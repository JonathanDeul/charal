#!/usr/bin/env python3
"""Render saved contextual-model results as reviewable Markdown summaries."""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'data/research/harmonization_v3'
NAMES={'seasonal_ratio':'Seasonal ratio (same purged fitting rows)','boost_point':'Boosting / no context',
    'boost_context':'Boosting / context','mlp_poisson':'MLP / no context / Poisson',
    'cnn_poisson':'CNN / context / Poisson','cnn_nb':'CNN / context / learned NB dispersion',
    'cnn_poisson_aggregate':'CNN / context / Poisson + regional monthly loss'}


def main():
    r=json.loads((OUT/'report.json').read_text());sp=json.loads((OUT/'spatial_audit.json').read_text())
    old=json.loads((ROOT/'data/research/harmonization_v2/report.json').read_text())
    tr=r['training'];best=r['selected_candidate'];b=r['selection']['seasonal_ratio'];win=r['selection'][best]
    verification=json.loads((OUT/'verification.json').read_text()) if (OUT/'verification.json').exists() else {}
    lines=['# Daily spatial/temporal context experiment — 15 November 2026','',
        f"**Selection winner: {NAMES[best]}.** Selection statewide monthly MAE: {win['monthly_mae']:.2f}, versus {b['monthly_mae']:.2f} for the seasonal control fitted on the identical purged daily training rows. This is an exploratory follow-up; production was not changed.",'',
        '## Design and data','',
        'All seven methods predict daily SNPP VIIRS counts in the same 224 California state-clipped 0.5° cells. Daily predictions are summed to calendar months for the primary metric. Input center values match the California-clipped archive exactly. Context contains MODIS from the five-state western union, using seven days (−3 through +3) and a 5×5 cell patch. At this coarse resolution the patch spans 2.5°; it is a regional context experiment, not precise fire-front reconstruction.',
        '', 'Four input channels: Terra count, Aqua count, FRP sum, and daytime count. The fifth channel marks source/domain/split availability, **not** cloud-free observation. Inputs are fixed log1p transforms. Both architectures also receive fixed cell coordinates, ecological-region indicators and calendar-month sine/cosine. No year, VIIRS values, CAL FIRE values or observation-mask pilot data are input features.', '',
        'Boosting with context receives the flattened **same full patch** as the CNN; no neighborhood information is withheld from it. The point controls receive the same central-day channels and static features. The contextual CNN has one 8-filter 3×3 spatial convolution over the 35 day/channel planes, followed by a 24-unit hidden layer. This is a compact first configuration, not an exhaustive neural-network search. The point network is a small MLP. The neural count mean is a seasonal-ratio signal times a learned correction plus a context-dependent positive additive term.', '',
        '- Development fit: 2013–2018; epoch choice: 2019–2020 from 2, 4, 8 epochs.',
        '- Final fit: 2013–2020; family selection: 2021–2022.',
        '- Known benchmark: 2023–2025; backward audit: February–December 2012, eligible months only.',
        '- All evaluated target months pass the original independently sourced MODIS/SNPP outage policy. All days in those months are evaluated, including double-zero days.',
        '- Source context cannot cross the split-year boundaries. The +3-day context makes this a **retrospective reconstruction**, not a real-time predictor.',
        '- All periods have been inspected in previous work; this follow-up does not manufacture a pristine independent test.', '',
        f"Daily archive: {r['manifest']['daily_ca_rows']:,} California cell-days across 2012–2025. Every full reference month's central MODIS and VIIRS totals were checked against v2. Development training retains {tr['development']['rows']:,} rows after purging {tr['development']['purged_rows']:,}; final training retains {tr['final']['rows']:,} after purging {tr['final']['purged_rows']:,}.", '',
        f"For stochastic/boosted fitting, all rows with local MODIS>0 or VIIRS>0 plus a seeded 10% sample of double-zero rows are used, with inverse-probability weights. This gives {tr['development_sample_rows']:,} development and {tr['final_sample_rows']:,} final fitting examples. Boosting and neural families share this sample; the common ratio anchor is estimated on all remaining fitting rows. Evaluation is completely unsampled. The aggregate-loss variant additionally optimizes full training-month north/south log-total disagreement with weight 0.1, using all remaining rows after event purging and without negative sampling; this entails extra optimizer steps and is not a compute-matched loss-only comparison.", '',
        '## CAL FIRE use and boundary guard','',
        f"CAL FIRE is used **only for split protection and descriptive evaluation**. Records are connected by normalized IRWIN and complex IDs; there are {tr['calfire_linked_groups']:,} linked groups. Final geometry/area are never provided to a predictor or substituted for VIIRS labels. Final fitting excludes spatial/temporal input supports associated with {len(tr['final']['crossing_groups'])} known linked groups touching a later audit period. The spatial guard expands by the context radius; the temporal guard expands by three days.", '',
        'Unknown start/end dates fall back conservatively to the source year bounds. Missing linkage metadata, unreported fires and coarse final geometries prevent a guarantee of event independence. The large-event diagnostic selects cell-days intersecting final reported perimeters during their reported alarm-to-containment interval, with maximum linked-record area ≥10,000 ha. It is not a daily burned-area truth or an independent sample of fires.', '',
        '## Main results','',
        'MAE below is the absolute error of the statewide **monthly total**, in reported detections. WAPE divides summed absolute monthly errors by summed reference counts.', '',
        '| Method | Selection 2021–22 MAE | Known 2023–25 MAE | Known 2023–25 WAPE | Backward 2012 MAE |',
        '| --- | ---: | ---: | ---: | ---: |']
    for name in r['protocol']['models']:
        a,t,h=[r[k][name] for k in ['selection','known_benchmark','backward_audit']]
        lines.append(f"| {NAMES[name]} | {a['monthly_mae']:.2f} | {t['monthly_mae']:.2f} | {t['monthly_wape']:.2%} | {h['monthly_mae']:.2f} |")
    lines+=['',f"For reference, the **unchanged deployed v1 ratio** has selection MAE {old['selection']['seasonal_ratio']['monthly_mae']:.2f} and known-benchmark MAE {old['benchmark']['seasonal_ratio']['monthly_mae']:.2f}. V3's ratio is refitted after the new event guard; differences between these controls must not be attributed to context or a neural architecture.",'',
        '### Context comparisons','', '| Comparison | Selection MAE change with context | Known benchmark MAE change with context |','| --- | ---: | ---: |']
    for control,context,label in [('boost_point','boost_context','Boosting: point → full patch'),('mlp_poisson','cnn_poisson','Neural: point MLP → patch CNN, Poisson')]:
        changes=[1-r[k][context]['monthly_mae']/r[k][control]['monthly_mae'] for k in ['selection','known_benchmark']]
        lines.append(f"| {label} | {changes[0]:+.1%} | {changes[1]:+.1%} |")
    if 'calfire_guard_effect' in verification:
        g=verification['calfire_guard_effect']
        lines+=['',f"The event guard removes {1-g['rows_after']/g['rows_before']:.1%} of training cell-days, but {1-g['reference_after']/g['reference_before']:.1%} of training VIIRS reports and {1-g['modis_after']/g['modis_before']:.1%} of MODIS reports. Event removal can therefore substantially shift the activity distribution. Comparing v3 directly with v1 combines an architecture/input change with a training-data change; the within-v3 controls are the fair architectural comparison.",'']
    lines+=['','Positive percentages mean lower error with context. The neural comparison changes architecture along with input support; the boosting comparison isolates adding the patch to the same estimator settings. Agreement or disagreement across these comparisons is more informative than a single winner.', '',
        '### Regional and local safeguards','', '| Method | Selection north monthly MAE | Selection south monthly MAE | Selection cell-month MAE | Known cell-month MAE |','| --- | ---: | ---: | ---: | ---: |']
    for name in r['protocol']['models']:
        s,t=r['selection'][name],r['known_benchmark'][name]
        lines.append(f"| {NAMES[name]} | {s['north']['monthly_mae']:.2f} | {s['south']['monthly_mae']:.2f} | {s['cell_month']['mae']:.2f} | {t['cell_month']['mae']:.2f} |")
    for split in ['selection','known_benchmark']:
        lines+=['',f'### Zero-MODIS and high-activity diagnostics: {split}','',
            '| Method | Zero-MODIS day MAE | Zero-MODIS month MAE | ≥500 MODIS/month MAE | ≥500 MODIS/month signed bias | Large-event daily MAE |',
            '| --- | ---: | ---: | ---: | ---: | ---: |']
        for name in r['protocol']['models']:
            s=r[split][name];h=s['high_activity_month'];event=s['large_event_daily']
            bias=h['bias_total']/max(h['reference_total'],1)
            lines.append(f"| {NAMES[name]} | {s['zero_modis_daily']['cell_daily_mae']:.3f} | {s['zero_modis_month']['mae']:.2f} | {h['mae']:.2f} | {bias:+.1%} | {event['cell_daily_mae']:.3f} |")
        baseline=r[split]['seasonal_ratio']
        lines+=['',f"High-activity group: {baseline['high_activity_month']['n']} cell-months. Negative bias indicates underprediction of the group's total; it can conceal large individual over/under errors. Daily-zero and month-zero strata differ: a month can have positive MODIS totals while many individual days have none. Large-event stratum: {baseline['large_event_daily']['n']:,} cell-days.",'']
    zero_diagnostics={}
    lines+=['## Distinguishing VIIRS-only activity from truly empty cell-months','',
        'This target-conditioned diagnostic is descriptive only. No VIIRS presence is used as an inference feature.', '',
        '| Period | Group (MODIS=0) | Cell-months | Actual VIIRS | Boost point predicted | Boost context predicted | Boost point MAE | Boost context MAE |',
        '| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for split in ['selection','known_benchmark']:
        frame=pd.read_csv(OUT/f'{split}_predictions.csv.gz')
        cm=frame.groupby(['month','cell'])[['modis_count','viirs_count',*r['protocol']['models']]].sum()
        zero_diagnostics[split]={}
        for label,mask in [('Both zero',cm.modis_count.eq(0)&cm.viirs_count.eq(0)),('VIIRS positive',cm.modis_count.eq(0)&cm.viirs_count.gt(0))]:
            a=cm[mask];stats={'n':len(a),'reference_total':float(a.viirs_count.sum()),'models':{}}
            for name in r['protocol']['models']:
                stats['models'][name]={'predicted_total':float(a[name].sum()),'mae':float((a[name]-a.viirs_count).abs().mean())}
            zero_diagnostics[split][label]=stats
            p,c=stats['models']['boost_point'],stats['models']['boost_context']
            lines.append(f"| {split} | {label} | {len(a):,} | {a.viirs_count.sum():,.0f} | {p['predicted_total']:,.0f} | {c['predicted_total']:,.0f} | {p['mae']:.2f} | {c['mae']:.2f} |")
    (OUT/'zero_modis_diagnostics.json').write_text(json.dumps(zero_diagnostics,indent=2))
    lines+=['','A lower predicted total is not automatically worse: a model can reduce erroneous positive expectations at the wrong locations. Compare absolute error in VIIRS-positive and genuinely empty groups separately. The seasonal ratio always predicts zero in both groups, so it sacrifices VIIRS-only activity but incurs no error in the much larger truly empty group. Context improves both groups relative to point boosting here, while the combined zero-MODIS MAE can still be worse than the ratio control.','']
    lines+=['## Seed stability and training','', '| Neural family | Chosen epochs | Selection monthly MAE by seed 42 / 43 / 44 | Ensemble selection MAE |','| --- | ---: | --- | ---: |']
    for name,seed_scores in r['selection_seed_metrics'].items():
        scores=[seed_scores[str(seed)]['monthly_mae'] for seed in r['protocol']['seeds']]
        lines.append(f"| {NAMES[name]} | {r['selected_epochs'][name]} | {' / '.join(f'{x:.1f}' for x in scores)} | {r['selection'][name]['monthly_mae']:.1f} |")
    hist=json.loads((OUT/'final_histories.json').read_text())
    alphas=[hist['cnn_nb'][str(seed)][-1]['alpha'] for seed in r['protocol']['seeds']]
    lines+=['',f"Learned global NB2 dispersion by seed: {', '.join(f'{a:.4f}' for a in alphas)}. Seed variation measures optimizer sensitivity, not independent-data confidence intervals. Main experiment runtime: {r['elapsed_seconds']/60:.1f} minutes on CPU with four Torch threads. No test-time fitting or calibration was performed.",'',
        '## Spatial transfer diagnostic','',
        f"Refit on {sp['train_cells']} California cells whose centers are more than 2° (maximum-coordinate distance) from every northern audit cell. This separates full 5×5 input patches geographically. Fit 2013–2020; evaluate northern California in 2023–2025. Training rows: {sp['train_rows']:,}; audit rows: {sp['evaluation_rows']:,}. Neural epochs are reused from the main development stage, which included northern CA in earlier years: this is a fixed-configuration transfer check, not wholly unseen-geography model development.", '',
        '| Method | Northern transfer monthly MAE | Northern transfer WAPE |', '| --- | ---: | ---: |']
    for name,s in sp['metrics'].items():lines.append(f"| {NAMES[name]} | {s['monthly_mae']:.2f} | {s['monthly_wape']:.2%} |")
    lines+=['','## Reproduce and inspect','',
        '```sh','.venv/bin/python -m pip install -r requirements-research.txt',
        '.venv/bin/python scripts/prepare_harmonization_v3.py','.venv/bin/python scripts/train_harmonization_v3.py',
        '.venv/bin/python scripts/audit_harmonization_v3_spatial.py','.venv/bin/python scripts/verify_harmonization_v3.py','.venv/bin/python scripts/report_harmonization_v3.py',
        '.venv/bin/python -m pytest tests -q','```','',
        '- Frozen main protocol: `research/harmonization_v3/protocol.json`.',
        '- Supplementary transfer protocol: `research/harmonization_v3/spatial_audit_protocol.json`, specified during development before final selection results.',
        '- Main report and per-day unsampled predictions: `data/research/harmonization_v3/report.json` and `*_predictions.csv.gz`.',
        '- Selection sealed before benchmark/backward predictions: `data/research/harmonization_v3/selection.json`.',
        '- Every neural fit checkpoint: `models/harmonization_v3/*.pt`; final boosted fits: `*.pkl`.',
        '- Per-epoch timings/losses and learned dispersion: `histories.json` / `final_histories.json` in the research data folder.',
        '', 'Production estimator, calendar payload and application are preserved. Full observing exposure is still unknown. A zero report is not proof of no fire or a clear-sky observation. More epochs, finer grids and alternate contexts remain untested; unfavorable results here do not establish that neural methods cannot help.', '']
    (ROOT/'docs/HARMONIZATION_V3.md').write_text('\n'.join(lines))
    compact={'selected_candidate':best,'production_changed':False,'models':{name:{'selection_monthly_mae':r['selection'][name]['monthly_mae'],
        'known_benchmark_monthly_mae':r['known_benchmark'][name]['monthly_mae'],'known_benchmark_wape':r['known_benchmark'][name]['monthly_wape'],
        'spatial_monthly_mae':sp['metrics'][name]['monthly_mae']} for name in r['protocol']['models']}}
    (OUT/'summary.json').write_text(json.dumps(compact,indent=2))
    print('Saved docs/HARMONIZATION_V3.md and summary.json')


if __name__=='__main__':main()
