#!/usr/bin/env python3
"""Verify completed MPS neural rounds, report failures as well as successes."""
from pathlib import Path
import hashlib,json,sys
import numpy as np
import pandas as pd
import torch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend.harmonization_v5 import MonthData,NeuralHurdle
from backend.harmonization_v6 import RegionalCountNet
from backend.harmonization_v7 import EmbeddedHurdle
from scripts.train_harmonization_v2 import diagnostics


def cpu_predict(net,t,idx):
    net.eval();values=[]
    with torch.no_grad():
        for i in range(0,len(idx),2):
            ids=idx[i:i+2];mu=net(t['x'][ids],t['base'][ids],t['has'][ids],t['temporal'][ids])[0];values.append(mu.numpy())
    return np.concatenate(values).reshape(-1)


def main():
    torch.set_num_threads(4);torch.backends.mha.set_fastpath_enabled(False)
    data=MonthData(ROOT);reports={};checks={};all_candidates=[]
    baseline=json.loads((ROOT/'data/research/harmonization_v4/report.json').read_text())
    for study in ['v5','v6','v7']:
        directory=ROOT/f'data/research/harmonization_{study}';path=directory/'report.json'
        if not path.exists():continue
        r=json.loads(path.read_text());reports[study]=r
        assert r['device']=='mps'
        assert r['protocol_sha256']==hashlib.sha256((ROOT/f'research/harmonization_{study}/protocol.json').read_bytes()).hexdigest()
        for source,digest in r['source_sha256'].items():assert hashlib.sha256((ROOT/source).read_bytes()).hexdigest()==digest
        sealed=json.loads((directory/'selection.json').read_text());assert not sealed['known_benchmark'] and not sealed['backward_audit']
        winner=r['selected_candidate'];split_checks={}
        for split,years in [('selection',[2021,2022]),('known_benchmark',[2023,2025]),('backward_audit',[2012,2012])]:
            frame=pd.read_csv(directory/f'{split}_predictions.csv.gz');expected=data.evaluated_frame(data.indices(years))
            np.testing.assert_array_equal(frame[['date','gy','gx']].to_numpy(),expected[['date','gy','gx']].to_numpy())
            np.testing.assert_array_equal(frame.viirs_count.to_numpy(),expected.viirs_count.to_numpy())
            score=diagnostics(expected,frame.candidate.to_numpy())
            for metric in ['monthly_mae','monthly_wape','cell_month_mae']:assert np.isclose(score[metric],r[split][winner][metric],rtol=1e-5,atol=1e-4)
            split_checks[split]={'rows':len(frame),'reference_and_metric_parity':True}
        # Reproduce an ensemble on three complete months, preserving spatial
        # attention support. Comparing sampled cells alone would be invalid.
        idx=data.indices([2021,2022])[:3];predictions=[]
        for seed in r['protocol']['seeds']:
            ck=torch.load(ROOT/f'models/harmonization_{study}/final_{winner}_{seed}.pt',map_location='cpu',weights_only=True)
            inputs={k:np.array(v,np.float32) if k!='columns' else v for k,v in ck['inputs'].items()}
            cfg=ck['config'];n=len(inputs['columns'])
            if study=='v5':net=NeuralHurdle(n,cfg['architecture'])
            elif study=='v6':net=RegionalCountNet(n,cfg['architecture'],torch.from_numpy(data.north))
            else:net=EmbeddedHurdle(n,cfg['architecture'],ck['state_dict']['knots'])
            net.load_state_dict(ck['state_dict']);t=data.tensors(inputs,'cpu')
            pred=cpu_predict(net,t,idx);predictions.append(pred)
            altered=dict(t);altered['y']=torch.full_like(t['y'],1e12)
            np.testing.assert_array_equal(cpu_predict(net,altered,idx),pred)
        expected=pd.read_csv(directory/'selection_predictions.csv.gz').candidate.to_numpy()[:len(idx)*data.C]
        actual=np.mean(predictions,axis=0)
        np.testing.assert_allclose(actual,expected,rtol=5e-4,atol=1e-4)
        checks[study]={'device_recorded':'mps','protocol_and_source_hashes':True,'selection_sealed_before_audits':True,
            'checkpoint_ensemble_matches':True,'checkpoint_max_absolute_MPS_CPU_difference':float(np.abs(actual-expected).max()),
            'reference_input_invariance':True,'splits':split_checks}
        for name,s in r['selection'].items():all_candidates.append((study,name,s))
    best=min(all_candidates,key=lambda a:a[2]['monthly_mae']);study,winner,score=best
    r=reports[study];threshold=score['monthly_mae']<500
    # Each round audits its own chosen winner only. The best selection candidate
    # must therefore have a corresponding locked known-benchmark result.
    assert winner==r['selected_candidate']
    output=ROOT/'data/research/neural_summary';output.mkdir(exist_ok=True)
    summary={'best_study':study,'best_candidate':winner,'threshold_met':threshold,'selection_mae':score['monthly_mae'],
        'known_benchmark_mae':r['known_benchmark'][winner]['monthly_mae'],'production_changed':False,'checks':checks}
    references={'selection':baseline['baseline_selection'],'known_benchmark':baseline['audits']['known_benchmark']['baseline'],
        'backward_audit':baseline['audits']['backward_audit']['baseline']}
    summary['relative_to_deployed']={}
    for label,reference in references.items():
        measured=r[label][winner]
        summary['relative_to_deployed'][label]={'monthly_mae_change':measured['monthly_mae']/reference['monthly_mae']-1,
            'cell_mae_change':measured['cell_month_mae']/reference['cell_month_mae']-1,
            'regional_changes':{region:measured['regions'][region]['monthly_mae']/reference['regions'][region]['monthly_mae']-1 for region in ['north','south']}}
    (output/'summary.json').write_text(json.dumps(summary,indent=2))
    if study=='v7' and winner=='plr_mlp_conditional':
        from backend.neural_candidate import NeuralCandidate
        sample=pd.read_csv(ROOT/'data/research/harmonization_v7/selection_predictions.csv.gz')
        frame=data.evaluated_frame(data.indices([2021,2022]))
        public=NeuralCandidate(ROOT).predict(frame)
        np.testing.assert_allclose(public,sample.candidate.to_numpy(),rtol=5e-4,atol=1e-4)
        summary['portable_inference_verified']=True
        (output/'summary.json').write_text(json.dumps(summary,indent=2))
        manifest={'architecture':'Piecewise-linear numeric embeddings, two64-unit ReLU layers, neural presence/conditional-count heads',
            'seeds':[42,43,44],'weights':[1/3]*3,'boosted_teacher':False,'training_years':[2013,2020],
            'requires':'MODIS-derived v4 feature table; VIIRS/year ignored, no labels needed for inference',
            'loader':'backend.neural_candidate.NeuralCandidate(root, device="cpu" or "mps").predict(frame)',
            'checkpoints':{str(seed):{'path':f'models/harmonization_v7/final_plr_mlp_conditional_{seed}.pt',
                'sha256':hashlib.sha256((ROOT/f'models/harmonization_v7/final_plr_mlp_conditional_{seed}.pt').read_bytes()).hexdigest()} for seed in [42,43,44]}}
        (output/'candidate_manifest.json').write_text(json.dumps(manifest,indent=2))
    lines=['# MPS neural harmonization experiments','',
        f"**Best completed neural candidate: {study} / {winner}.** Statewide 2021–2022 monthly MAE: **{score['monthly_mae']:.2f}**. Target <500: **{threshold}**. This is the average of three fixed neural seeds, not a lucky selected seed. Production remains unchanged.", '',
        '## GPU verification and evaluation policy','',
        'The sandbox reports `mps.is_available() == False`, while the authorized outer execution environment reports built=True, available=True. A real MPS matrix forward/backward smoke test succeeded. All rounds below require MPS and raise on unavailability; there is no silent CPU fallback. Inputs, weights and training gradients are placed on MPS. Checkpoints are saved on CPU for portability; independent CPU inference reproduces their saved MPS ensemble predictions within float32 tolerance.', '',
        'Training uses the same complete paired-month 2013–2020 observations as the deployed seasonal calibration. Development fits 2013–2018; 2019–2020 selects epochs. The resulting epochs are used for fresh 2013–2020 fits. Each config is evaluated on 2021–2022; the config choice is saved before new winner-only benchmark predictions. Each round has three seeds. No 2021+ labels receive training gradients. All historical periods have been repeatedly inspected, so <500 is an exploratory development target, not a pristine independent test or guaranteed future accuracy.', '',
        'All eligible 224 cells are used in full-month batches, including zeros. The primary score is statewide monthly mean absolute error over the 20 eligible 2021–2022 months, maintaining the original conservative outage policy. No error-based month removal is applied.', '',
        '## Architectures and objective','',
        '- V5: pure neural hurdle-style count mean with fine MODIS descriptors; MLP, full-cell spatial Transformer, and four-day temporal-patch Transformer. No boosted teacher or boosted predictions. Joint local Poisson, binary-presence and direct statewide/north/south monthly losses.',
        '- V6: neural regional totals from weighted pooling or multihead query/key/value attention, with baseline-relative or bounded neural cell allocation. Attention pooling is not mislabeled as the full spatial/temporal Transformer encoder used in v5. Fixed allocation leaves zero-MODIS cells near zero and cannot reconstruct missed detections.',
        '- V7: train-only piecewise-linear numeric embeddings, a per-cell feature-token Transformer or MLP, and positive-target-only conditional-count regression plus presence and aggregate objectives. The feature Transformer attends between input variables rather than between geographic cells or days.', '',
        'The training-only seasonal ratio is a count offset and extrapolation anchor, not a boosted model. Every candidate learns its presence/count corrections through neural weights and backpropagation. Probabilities are model components and have not been independently calibrated as physical fire probabilities.', '',
        '## Completed candidates','',
        '| Round | Neural config | Selected epoch | 2021–2022 monthly MAE | North monthly MAE | South monthly MAE | Cell-month MAE |',
        '| --- | --- | ---: | ---: | ---: | ---: | ---: |']
    for study,name,s in all_candidates:
        epochs=reports[study].get('chosen_epochs',reports[study].get('selected_epochs'))
        lines.append(f"| {study} | {name} | {epochs[name]} | {s['monthly_mae']:.2f} | {s['regions']['north']['monthly_mae']:.2f} | {s['regions']['south']['monthly_mae']:.2f} | {s['cell_month_mae']:.2f} |")
    lines+=['', '## Locked winner audits','', '| Round winner | 2021–2022 MAE | Known 2023–2025 MAE | Backward 2012 MAE |', '| --- | ---: | ---: | ---: |']
    for study,rnd in reports.items():
        name=rnd['selected_candidate'];a,t,b=[rnd[k][name]['monthly_mae'] for k in ['selection','known_benchmark','backward_audit']]
        lines.append(f"| {study} / {name} | {a:.2f} | {t:.2f} | {b:.2f} |")
    lines+=['', 'Deployed seasonal calibration: selection MAE 730.71, known benchmark 291.33, backward 204.77. V4 boosted candidate: 666.33, 259.74, 165.37. The v4 post-selection fine-feature boosting ablation scored 524.31 on selection only; it was never independently benchmark-confirmed and is not the currently deployed calibration.', '',
        '## Best neural candidate details','', '| Period | Statewide MAE | WAPE | North MAE | South MAE | Cell-month MAE |', '| --- | ---: | ---: | ---: | ---: | ---: |']
    r=reports[best[0]];name=best[1]
    for label in ['selection','known_benchmark','backward_audit']:
        s=r[label][name];lines.append(f"| {label} | {s['monthly_mae']:.2f} | {s['monthly_wape']:.2%} | {s['regions']['north']['monthly_mae']:.2f} | {s['regions']['south']['monthly_mae']:.2f} | {s['cell_month_mae']:.2f} |")
    lines+=['', '| Seed | Selection monthly MAE |', '| --- | ---: |']
    for seed,s in r['seed_scores'][name].items():lines.append(f"| {seed} | {s['monthly_mae']:.2f} |")
    lines+=['', 'Seed differences show optimizer sensitivity, not independent-data confidence intervals. Greater attention capacity is not assumed to improve calibration: unfavorable full Transformer results are retained.', '',
        '## Material tradeoffs and unexecuted follow-up','',
        'Meeting the <500 statewide target does not satisfy every earlier production safeguard. The best v7 neural ensemble increases selection cell-month MAE from 7.67 to 8.23 (+7.3%). On the known benchmark, northern monthly MAE increases from 92.45 to 97.68 (+5.7%), while statewide and overall cell errors improve. Backward northern 2012 MAE increases from 62.20 to 110.96; statewide backward MAE nevertheless improves. These failures prevent describing this as a uniformly superior spatial reconstruction or silently replacing the deployed model.', '',
        'Selection signed monthly bias is approximately −418 detections/month, so the lower MAE comes with systematic underprediction. Single-seed selection MAEs range from356 to557; the reported475.51 is the predeclared equal-weight ensemble, not seed selection. Both numerical feature encoding and the changed positive-count objective distinguish v7 from the previous CNNs; the experiment does not establish that extra GPU compute alone caused the improvement.', '',
        'The initial v7 batch-two implementation was stopped before final selection and benchmark scoring when it was found to differ from the frozen batch-eight protocol. Its artifacts remain under `harmonization_v7_batch2_aborted`, explicitly excluded from the candidate search and result tables. Corrected batch-eight runs produced the results above.', '',
        'A separate Terra/Aqua feature preparation and modality-fusion architecture were prepared as a possible next round, but v8 was not trained after the v7 ensemble met the requested threshold. A public NASA POWER availability probe also succeeded; no POWER/weather values were used in any reported fit. The new raw-platform descriptors describe detected pixels, not cloud-free exposure.', '',
        '## Artifacts and sources','',
        'Each study has frozen `research/harmonization_vN/protocol.json`, complete `data/research/harmonization_vN/report.json`, sealed `selection.json`, per-epoch histories and per-cell winner predictions. Portable neural checkpoints are under `models/harmonization_vN/`. `data/research/neural_summary/summary.json` contains independent source/protocol, row/metric, checkpoint and target-invariance checks. `candidate_manifest.json` identifies the frozen v7 ensemble and checkpoint hashes. `backend.neural_candidate.NeuralCandidate(root).predict(frame)` provides CPU inference on the derived v4 MODIS feature table (MPS optional); it does not require VIIRS labels. No new uncertainty bands or physical exposure observations were added.', '',
        'Run `scripts/train_harmonization_v5.py --device mps`, `scripts/train_harmonization_v6.py` or `scripts/train_harmonization_v7.py` in the authorized MPS execution environment; then `scripts/report_neural_harmonization.py`. Checkpoint verifications run on CPU. All scripts use the project `.venv` and `requirements-research.txt`.', '',
        'Architecture references: [PatchTST](https://arxiv.org/abs/2211.14730), [Earthformer](https://arxiv.org/abs/2207.05833). These experiments are small custom count-regression models, not reproductions or pretrained weights of those systems. [PyTorch MPS documentation](https://docs.pytorch.org/docs/stable/notes/mps.html) distinguishes compiled support from runtime device availability.', '']
    (ROOT/'docs/HARMONIZATION_NEURAL.md').write_text('\n'.join(lines))
    print('Verified completed neural studies; best',best[0],best[1],score['monthly_mae'],'threshold',threshold)


if __name__=='__main__':main()
