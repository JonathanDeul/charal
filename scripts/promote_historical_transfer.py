#!/usr/bin/env python3
"""Verify and export the passing local release, retaining exact v1 restoration."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,gzip,hashlib,json,pickle,sys
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend.release_export import export_release
from backend.historical_transfer import HistoricalTransfer
OUT=ROOT/'data/research/harmonization_release';DATA=ROOT/'data/processed';MDIR=ROOT/'models/harmonization_release'


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--restore',action='store_true');args=parser.parse_args()
    snapshot=OUT/'original_analysis.json.gz';packed=OUT/'original_runtime_analysis.json.gz'
    if args.restore:
        if not snapshot.exists() or not packed.exists():raise ValueError('No preserved original snapshot')
        (DATA/'analysis.json').write_bytes(gzip.decompress(snapshot.read_bytes()));(DATA/'analysis.json.gz').write_bytes(packed.read_bytes())
        restored={'id':'original-v1','estimator':'models/harmonization.pkl','scientific_sha256':sha(DATA/'analysis.json'),
            'runtime_sha256':sha(DATA/'analysis.json.gz'),'restored_from':'data/research/harmonization_release/original_analysis.json.gz'}
        (MDIR/'active_manifest.json').write_text(json.dumps(restored,indent=2))
        print('Restored exact original scientific/runtime analysis');return
    report=json.loads((OUT/'report.json').read_text());uncert=json.loads((OUT/'uncertainty.json').read_text())
    if not report['all_gates_passed']:raise ValueError('Candidate failed promotion criteria')
    if report['protocol_sha256']!=sha(ROOT/'research/harmonization_release/protocol.json'):raise ValueError('Release protocol changed')
    source_paths=['data/research/harmonization_v4/cells.csv.gz','models/harmonization_v4/hurdle_rich.pkl','models/harmonization.pkl','research/harmonization_release/protocol.json']
    hashes={p:sha(ROOT/p) for p in source_paths}
    current=json.loads((DATA/'analysis.json').read_text())
    if current['harmonization'].get('release',{}).get('id')=='historical-transfer-1':
        if current['harmonization']['release']['source_hashes']!=hashes:raise ValueError('Source inputs changed; retrain before replacing release')
        # Current non-harmonization fields may have changed independently. Keep
        # them while rebuilding only this release's own scientific object.
        original=json.loads(gzip.decompress(snapshot.read_bytes()))
        current['harmonization']=original['harmonization']
    elif not snapshot.exists():
        snapshot.write_bytes(gzip.compress((DATA/'analysis.json').read_bytes(),mtime=0));packed.write_bytes((DATA/'analysis.json.gz').read_bytes())
    else:
        original=json.loads(gzip.decompress(snapshot.read_bytes()))
        if current['input_sha256']!=original['input_sha256']:raise ValueError('Prepared source snapshot changed; cannot apply stale release')
    manifest=json.loads((ROOT/'data/research/harmonization_v4/manifest.json').read_text())
    if sha(DATA/'hotspots.csv')!=manifest['input_sha256']['data/processed/hotspots.csv']:raise ValueError('Hotspot source changed')
    f=pd.read_csv(ROOT/'data/research/harmonization_v4/cells.csv.gz',dtype={'ecoregion':str})
    with (MDIR/'candidate.pkl').open('rb') as handle:package=pickle.load(handle)
    if package['report_sha256']!=sha(OUT/'report.json'):raise ValueError('Candidate/report mismatch')
    if package['model'].choice!=report['choice']:raise ValueError('Candidate/selection mismatch')
    if package['uncertainty']!=uncert['residual_calibration']:raise ValueError('Candidate/uncertainty mismatch')
    if sha(OUT/'bootstrap_predictions.npz')!=uncert['bootstrap']['cache_sha256']:raise ValueError('Bootstrap cache changed')
    model=package['model'];p=model.predict(f)
    cal=f[f.year.between(2021,2022)&f.pair_complete&f.viirs_count.notna()]
    score=np.abs(cal.viirs_count.to_numpy()-model.predict(cal))/np.sqrt(model.predict(cal)+1)
    report['local_diagnostic_q80']=float(np.quantile(score,.8));report['uncertainty_assessment']=uncert['assessment'];report['release_source_hashes']=hashes
    output=export_release(current,f,p,package['uncertainty'],report,uncert['bootstrap'])
    output['generated_at']=datetime.now(timezone.utc).isoformat()
    output['harmonization']['release']['bootstrap_refits']=uncert['bootstrap']['refits']
    # Validate scientific invariants before either runtime file is written.
    old=current['harmonization'];new=output['harmonization']
    for key in current:
        if key not in ['harmonization','generated_at']:assert output[key]==current[key]
    for a,b in zip(old['monthly'],new['monthly']):
        assert a['date']==b['date'] and a['modis_count']==b['modis_count'] and a['viirs_count']==b['viirs_count'] and a['source']==b['source']
        if a['source']!='modeled_modis':assert a['harmonized_count']==b['harmonized_count']
        if a['date']<'2002-07-01':assert np.isclose(a['modeled_count'],b['modeled_count'])
    totals={}
    for cell in new['cell_monthly']:
        if cell['harmonized_count'] is not None:totals[cell['date']]=totals.get(cell['date'],0)+cell['harmonized_count']
    for row in new['monthly']:
        if row['harmonized_count'] is not None:assert np.isclose(totals[row['date']],row['harmonized_count'])
    body=json.dumps(output,separators=(',',':'),allow_nan=False).encode();tmp=DATA/'analysis.release.tmp';tmp.write_bytes(body)
    runtime=gzip.compress(body,mtime=0);(DATA/'analysis.runtime.tmp').write_bytes(runtime)
    tmp.replace(DATA/'analysis.json');(DATA/'analysis.runtime.tmp').replace(DATA/'analysis.json.gz')
    active={'id':'historical-transfer-1','estimator':'models/harmonization_release/candidate.pkl','choice':report['choice'],
        'original_model':'models/harmonization.pkl (preserved v1 baseline)','scientific_sha256':sha(DATA/'analysis.json'),
        'runtime_sha256':sha(DATA/'analysis.json.gz'),'source_hashes':hashes,'restore_command':'.venv/bin/python scripts/promote_historical_transfer.py --restore'}
    active['artifact_hashes']={str(p.relative_to(ROOT)):sha(p) for p in [MDIR/'candidate.pkl',OUT/'report.json',OUT/'training_selection.json',OUT/'uncertainty.json']}
    (MDIR/'active_manifest.json').write_text(json.dumps(active,indent=2));(OUT/'promotion.json').write_text(json.dumps(active,indent=2))
    print('Promoted verified local historical-transfer-1; original observations, outages, extremes and pre-Aqua estimates preserved')


if __name__=='__main__':main()
