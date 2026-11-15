#!/usr/bin/env python3
"""Independently verify the frozen candidate and write a bounded result claim."""
from pathlib import Path
import hashlib
import json
import pickle
import sys
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend.harmonization_v4 import features
from scripts.train_harmonization_v2 import subset,diagnostics
from scripts.train_harmonization_v4 import gate
OUT=ROOT/'data/research/harmonization_v4'


def main():
    report=json.loads((OUT/'report.json').read_text());audit=json.loads((OUT/'audit.json').read_text())
    name=report['selected_candidate'];chosen=report['selection'][name]
    data=pd.read_csv(OUT/'cells.csv.gz',dtype={'ecoregion':str})
    with (ROOT/'models/harmonization_v4/candidate.pkl').open('rb') as h:package=pickle.load(h)
    with (ROOT/'models/harmonization.pkl').open('rb') as h:deployed=pickle.load(h)
    ratio=package['baseline'];model=package['model'];weight=package['weight']
    assert set(ratio.ratios)==set(deployed['ratios'])
    for month,value in ratio.ratios.items():assert np.isclose(value,deployed['ratios'][month],rtol=1e-12)
    assert report['protocol_sha256']==hashlib.sha256((ROOT/'research/harmonization_v4/protocol.json').read_bytes()).hexdigest()
    for path,digest in report['source_sha256'].items():assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==digest
    assert not json.loads((OUT/'selection.json').read_text())['audits']
    verification={'deployed_ratio_parameter_parity':True,'protocol_and_source_hashes':True,'pre_audit_selection_sealed':True,'splits':{}}
    rows=[]
    for label,years in [('selection',[2021,2022]),('known_benchmark',[2023,2025]),('backward_audit',[2012,2012])]:
        f=subset(data,years);b=ratio.predict(f);p=(1-weight)*b+weight*model.predict(f)
        assert np.isfinite(p).all() and (p>=0).all()
        changed=f.assign(viirs_count=1e12,year=1900)
        np.testing.assert_array_equal(model.predict(changed),model.predict(f))
        pred=diagnostics(f,p);base=diagnostics(f,b)
        saved=chosen if label=='selection' else report['audits'][label]['candidate']
        for metric in ['monthly_mae','monthly_wape','cell_month_mae']:assert np.isclose(pred[metric],saved[metric])
        old=pd.read_csv(OUT/f'{label}_predictions.csv.gz')
        if label=='selection':np.testing.assert_allclose(old[chosen['family']].to_numpy(),model.predict(f))
        else:np.testing.assert_allclose(old.candidate.to_numpy(),p)
        verification['splits'][label]={'n_cell_months':len(f),'metrics_and_saved_predictions_match':True,'gate':gate(pred,base)}
        rows.append((label,pred,base))
    assert all(verification['splits']['selection']['gate'].values())
    assert all(verification['splits']['known_benchmark']['gate'].values())
    sp=audit['spatial'];assert sp['minimum_center_distance']>2
    assert sp['candidate']['monthly_mae']<=1.05*sp['baseline']['monthly_mae']
    for label in ['selection','known_benchmark']:
        g=audit['guarded_sensitivity'][label];assert all(gate(g['candidate'],g['baseline']).values())
    # Conditional positive-count means must not fall below their natural support.
    applicable=data[data.viirs_count.notna()&data.pair_complete]
    conditional=(model.ratio.predict(applicable)+.05)*model.model.predict(features(applicable))
    assert conditional.min()>=1
    verification.update({'conditional_mean_minimum':float(conditional.min()),'no_reference_or_year_input_leakage':True,
        'spatial_noninferiority_5pct':True,'paired_event_guarded_improvement':True,'production_changed':False,
        'production_snapshot_sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in ['models/harmonization.pkl','data/processed/analysis.json','data/processed/analysis.json.gz']}})
    (OUT/'verification.json').write_text(json.dumps(verification,indent=2))
    # Full historical predictions remain research outputs. Source outages are
    # explicitly masked, and observed SNPP continues to be the reporting reference.
    old=json.loads((ROOT/'data/processed/analysis.json').read_text())['harmonization']['monthly']
    forecast=data[['date','gy','gx','modis_count','viirs_count']].copy();forecast['candidate_modeled_count']=(1-weight)*ratio.predict(data)+weight*model.predict(data)
    forecast.to_csv(OUT/'all_period_cell_predictions.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    totals=forecast.groupby('date').candidate_modeled_count.sum().to_dict()
    monthly=[]
    for row in old:
        date=row['date'];raw_prediction=float(totals[date]);available=row['harmonized_count'] is not None
        observation_reference=row['source'] not in ['modeled','modis_model'] and date>='2012-02-01'
        monthly.append({'date':date,'source':row['source'],'baseline_harmonized_count':row['harmonized_count'],
            'candidate_modeled_count':raw_prediction,'candidate_harmonized_count':None if not available else row['viirs_count'] if observation_reference else raw_prediction,
            'uncertainty':'No new calibrated uncertainty band; do not reuse v1 residual bands.'})
    pd.DataFrame(monthly).to_csv(OUT/'historical_comparison.csv',index=False)
    lines=['# Harmonization v4 — improved exploratory candidate','',
        f"**Frozen candidate: `{name}`.** A two-stage boosted conditional-mean model improves statewide monthly MAE on both 2021–2022 and the already-known 2023–2025 benchmark. It also improves aggregate north/south errors and overall cell-month MAE in both periods. This is an empirical improvement on inspected historical data, not proof of prospective superiority. Production is preserved.",'',
        '## Model and inputs','',
        'Stage 1 predicts the probability of at least one retained SNPP VIIRS report. Stage 2 predicts the conditional mean count given positive activity, using a Poisson boosted regression on positive-target training rows with a seasonal-ratio offset. The final expected count is probability × conditional mean. This is a hurdle-style mean estimator; it is not a fully fitted zero-truncated count-distribution likelihood. There is no hard presence threshold at inference.', '',
        'Inputs are MODIS-only: the v2 count/FRP/acquisition/geometry features; occupied 0.05° subcells within each 0.5° cell; 8-connected component counts and largest component; FRP quantiles; brightness-minus-background thermal contrast; mean confidence; within-month maximum daily activity and concentration; spatial neighbor totals at two radii; and previous-month/previous-three-month MODIS activity. Static coordinates and calendar-month cycles are included. VIIRS, year, CAL FIRE, and weather are not input predictors. Historical MODIS context before a split start is allowed because it contains no reference labels; no future month is used.', '',
        'The 0.05° grid is a descriptor of archived point locations, not additional satellite resolution or reconstructed missing fires. Neighbor counts are clipped to California; boundary support is fixed independently of observed fires. All model transforms and eligibility rules are reproducible. No external weather or vegetation data was necessary to obtain this candidate.', '',
        '## Search and evaluation','',
        'Six model families were tried: small/medium offset boosting with richer features, original-feature offset boosting, a two-stage hurdle model, and simple/rich Poisson linear regressions. Each was compared with five convex weights against the seasonal baseline (30 candidates). Linear regularization was chosen on temporal folds 2013–2016 → 2017–2018 and 2013–2018 → 2019–2020. The final family/weight was selected on 2021–2022, requiring ≥5% lower monthly MAE and no >5% cell/north/south degradation. All choices were saved before the selected candidate benchmark/backward predictions. Original eligibility/outage filtering and fitting years 2013–2020 are identical to the deployed calibration.', '',
        'These evaluation periods were inspected before this follow-up. The number of candidates and repeated use of selection years make the gain exploratory. A future untouched period is needed for independent confirmation. Earlier temporal-fold results are fully retained, including unfavorable ones.', '',
        '| Period | Baseline monthly MAE | Candidate monthly MAE | Improvement | Baseline cell MAE | Candidate cell MAE |',
        '| --- | ---: | ---: | ---: | ---: | ---: |']
    for label,p,b in rows:lines.append(f"| {label} | {b['monthly_mae']:.2f} | {p['monthly_mae']:.2f} | {1-p['monthly_mae']/b['monthly_mae']:.1%} | {b['cell_month_mae']:.2f} | {p['cell_month_mae']:.2f} |")
    lines+=['','| Period | Region | Baseline monthly MAE | Candidate monthly MAE |','| --- | --- | ---: | ---: |']
    for label,p,b in rows:
        for region in ['north','south']:lines.append(f"| {label} | {region} | {b['regions'][region]['monthly_mae']:.2f} | {p['regions'][region]['monthly_mae']:.2f} |")
    lines+=['','**Material backward-transfer limitation:** Northern California in 2012 worsens from 62.20 to 108.36 monthly MAE, despite a statewide improvement. Pre-2012 application cannot be directly verified with VIIRS. There is no claim that the candidate improves every ecosystem, event or historical regime.', '',
        '## Null inputs and extremes','',
        '| Period | Stratum | Baseline cell-month MAE | Candidate cell-month MAE | Candidate group signed bias |',
        '| --- | --- | ---: | ---: | ---: |']
    for label,s in audit['strata'].items():
        for group in ['all_zero_modis','viirs_only','both_zero','high_activity']:
            p,b=s['candidate'][group],s['baseline'][group]
            bias=f"{p['bias_fraction']:+.1%}" if p['bias_fraction'] is not None else 'undefined (zero reference total)'
            lines.append(f"| {label} | {group} | {b['mae']:.2f} | {p['mae']:.2f} | {bias} |")
    lines+=['','VIIRS-only cases improve, but predicted activity in truly empty cells makes the combined zero-MODIS stratum worse. High-activity absolute error is slightly worse on selection (27 cases) and better on the benchmark (only four cases); aggregate bias is closer to zero than the baseline in both periods. The missing-small-fire problem is not solved.', '',
        '## Confirmation and feature ablations','',
        f"Geographic transfer: refit only on centers >2° from northern audit cells, so 1° source-neighbor radii do not overlap. Candidate northern monthly MAE {sp['candidate']['monthly_mae']:.2f} versus paired baseline {sp['baseline']['monthly_mae']:.2f}; {sp['candidate']['monthly_mae']/sp['baseline']['monthly_mae']-1:+.1%}, within the fixed 5% tolerance. This diagnostic does not establish global geographic transfer.", '',
        f"CAL FIRE sensitivity drops an entire training cell-month if any daily input support is associated with a known cross-boundary linked event. It removes {audit['guarded_sensitivity']['removed_cell_months']:,} training cell-months. Paired refit results:", '',
        '| Period | Guarded baseline MAE | Guarded candidate MAE |', '| --- | ---: | ---: |']
    for label in ['selection','known_benchmark']:
        s=audit['guarded_sensitivity'][label];lines.append(f"| {label} | {s['baseline']['monthly_mae']:.2f} | {s['candidate']['monthly_mae']:.2f} |")
    lines+=['','Both guarded comparisons also pass the original statewide/cell/regional criteria. CAL FIRE remains a split-protection/evaluation source; incomplete links and dates prevent a guarantee of event independence.', '',
        'The following feature ablations were computed **after selection**, on 2021–2022 only, with fixed two-stage hyperparameters. They did not replace the frozen candidate or trigger another benchmark search.', '',
        '| Two-stage feature set | Selection monthly MAE |','| --- | ---: |']
    for label,s in audit['ablations'].items():lines.append(f"| {label} | {s['monthly_mae']:.2f} |")
    cv=next(x for x in report['development'][chosen['family']] if x['penalty']==report['chosen_penalties'][chosen['family']])
    lines+=['', 'Fine structure is promising; more neighboring/history features are not uniformly beneficial. The full selected model is not claimed to be the best possible feature subset.', '',
        f"The full candidate's mean temporal development-fold MAE is {cv['mean_mae']:.2f}, versus approximately 932.67 for the seasonal control in v2. Those shorter-training-fold results are unfavorable. Later-period improvements and the event-guard sensitivity therefore support a candidate for further prospective testing, not a universal model-superiority claim.", '',
        '## Artifacts and reproduce','',
        '```sh','.venv/bin/python scripts/prepare_harmonization_v4.py','.venv/bin/python scripts/train_harmonization_v4.py',
        '.venv/bin/python scripts/audit_harmonization_v4.py','.venv/bin/python scripts/report_harmonization_v4.py','.venv/bin/python -m pytest tests -q','```','',
        '- Frozen candidate package: `models/harmonization_v4/candidate.pkl` (trusted local pickle only).',
        '- Complete development and all 30 selection results: `data/research/harmonization_v4/report.json`.',
        '- Selection checkpoint sealed before new audits: `selection.json`.',
        '- Geographic, CAL FIRE and post-selection feature checks: `audit.json`.',
        '- Full-period research predictions and outage-masked historical comparison: `all_period_cell_predictions.csv.gz`, `historical_comparison.csv`.',
        '- Independent ratio parity, source/protocol hashes, saved predictions, reference/year input leakage and count-support verification: `verification.json`.',
        '- Production estimator and prepared calendar remain unchanged. New uncertainty bands have not been calibrated; existing baseline bands must not be reused for the candidate.', '']
    (ROOT/'docs/HARMONIZATION_V4.md').write_text('\n'.join(lines))
    summary={'candidate':name,'empirically_better_forward':True,'production_changed':False,
        'metrics':{label:{'baseline_mae':b['monthly_mae'],'candidate_mae':p['monthly_mae'],'improvement':1-p['monthly_mae']/b['monthly_mae']} for label,p,b in rows},
        'limitations':['Inspected historical periods and multiple comparisons; prospective confirmation needed.','Worse Northern California 2012.','Worse combined zero-MODIS absolute error.','Shorter-training temporal CV is unfavorable.']}
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2))
    print('Verified improved forward candidate, guarded sensitivity, and spatial tolerance; saved report and historical research outputs')


if __name__=='__main__':main()
