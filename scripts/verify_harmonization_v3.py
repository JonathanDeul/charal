#!/usr/bin/env python3
"""Check saved experimental artifacts independently of fitting."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
import torch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend.harmonization_v3 import DailyData,CountNet,metrics
from scripts.train_harmonization_v3 import predict_net
OUT=ROOT/'data/research/harmonization_v3'


def main():
    torch.set_num_threads(4)
    r=json.loads((OUT/'report.json').read_text());data=DailyData(ROOT)
    assert r['protocol_sha256']==hashlib.sha256((ROOT/'research/harmonization_v3/protocol.json').read_bytes()).hexdigest()
    for path,digest in r['source_sha256'].items():assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==digest
    selection=json.loads((OUT/'selection.json').read_text())
    assert not selection['known_benchmark'] and not selection['backward_audit']
    assert hashlib.sha256((OUT/'daily.npz').read_bytes()).hexdigest()==r['manifest']['daily_sha256']
    checks={}
    before,_=data.indices([2013,2020])
    after,_=data.indices([2013,2020],[[2021,2022],[2023,2025]])
    checks['calfire_guard_effect']={'rows_before':len(before),'rows_after':len(after),
        'reference_before':float(data.target.ravel()[before].sum()),'reference_after':float(data.target.ravel()[after].sum()),
        'modis_before':float(data.count.ravel()[before].sum()),'modis_after':float(data.count.ravel()[after].sum())}
    v2=pd.read_csv(ROOT/'data/research/harmonization_v2/cells.csv.gz',dtype={'ecoregion':str})
    for split,years in [('selection',[2021,2022]),('known_benchmark',[2023,2025]),('backward_audit',[2012,2012])]:
        frame=pd.read_csv(OUT/f'{split}_predictions.csv.gz')
        idx,_=data.indices(years)
        assert np.array_equal(frame.flat_index.to_numpy(),idx)
        # Daily sums reproduce independently prepared monthly reference counts.
        target=v2[v2.state.eq('CA')&v2.year.between(*years)&v2.pair_complete&v2.viirs_count.notna()]
        a=frame.groupby(['month','gy','gx']).viirs_count.sum().sort_index()
        b=target.assign(month=target.date.str[:7]).set_index(['month','gy','gx']).viirs_count.sort_index()
        np.testing.assert_array_equal(a.to_numpy(),b.to_numpy())
        for name in r['protocol']['models']:
            assert np.isfinite(frame[name]).all() and frame[name].ge(0).all()
            score=metrics(frame,frame[name].to_numpy())
            for key in ['monthly_mae','monthly_wape','cell_daily_mae','bias_total']:
                assert np.isclose(score[key],r[split][name][key],rtol=1e-6,atol=1e-5)
        checks[split]={'rows':len(frame),'monthly_reference_parity':True,'finite_predictions_and_metric_parity':True}
    # Load trusted local CNN checkpoints and reproduce a fixed sample of their
    # ensemble predictions without using any saved targets as input features.
    frame=pd.read_csv(OUT/'known_benchmark_predictions.csv.gz').sample(100,random_state=33)
    preds=[]
    for seed in r['protocol']['seeds']:
        ck=torch.load(ROOT/f'models/harmonization_v3/final_cnn_poisson_{seed}.pt',map_location='cpu',weights_only=True)
        model=CountNet(ck['nmeta'],ck['context'],ck['nb']);model.load_state_dict(ck['state_dict'])
        preds.append(predict_net(model,data,frame.flat_index.to_numpy(),[2023,2025],np.array(ck['ratios'],np.float32)))
    np.testing.assert_allclose(np.mean(preds,axis=0),frame.cnn_poisson.to_numpy(),rtol=1e-5,atol=1e-5)
    spatial=pd.read_csv(OUT/'spatial_predictions.csv.gz');sp=json.loads((OUT/'spatial_audit.json').read_text())
    for name in r['protocol']['models']:
        score=metrics(spatial,spatial[name].to_numpy())
        assert np.isclose(score['monthly_mae'],sp['metrics'][name]['monthly_mae'])
    assert sp['minimum_center_separation_degrees']>2
    checks.update({'checkpoint_prediction_parity':True,'spatial_patch_separation':True,
        'selection_sealed_before_benchmark':True,'protocol_and_source_hashes':True,'production_changed':False,
        'source_inputs_sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in ['data/processed/perimeters.json','data/processed/coverage.json','data/research/harmonization_v2/geography.json']}})
    (OUT/'verification.json').write_text(json.dumps(checks,indent=2))
    print('PASS: monthly reference parity, all unsampled row indices and metrics, checkpoint predictions, protocol/source hashes, and geographic patch separation')


if __name__=='__main__':main()
