#!/usr/bin/env python3
"""Freeze candidate selection before auditing the selected blend on known years."""
import os
os.environ.setdefault('OMP_NUM_THREADS','4');os.environ.setdefault('OPENBLAS_NUM_THREADS','4')
from pathlib import Path
import hashlib
import json
import pickle
import sys
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend.harmonization_v2 import SeasonalRatio,metrics
from backend.harmonization_v4 import make_model
from scripts.train_harmonization_v2 import diagnostics,subset
OUT=ROOT/'data/research/harmonization_v4';MDIR=ROOT/'models/harmonization_v4'
PROTOCOL=ROOT/'research/harmonization_v4/protocol.json'


def save(name,data):
    p=OUT/name;tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(data,indent=2,allow_nan=False));tmp.replace(p)


def gate(candidate,baseline):
    return {'monthly_improvement':candidate['monthly_mae']<=.95*baseline['monthly_mae'],
        'cell_noninferiority':candidate['cell_month_mae']<=1.05*baseline['cell_month_mae'],
        'regional_noninferiority':all(candidate['regions'][r]['monthly_mae']<=1.05*baseline['regions'][r]['monthly_mae'] for r in ['north','south'])}


def run():
    protocol=json.loads(PROTOCOL.read_text());MDIR.mkdir(exist_ok=True,parents=True)
    data=pd.read_csv(OUT/'cells.csv.gz',dtype={'ecoregion':str})
    # Past MODIS source inputs are permitted across a split's start boundary
    # in retrospective inference; no VIIRS history or future month is consumed.
    report={'protocol':protocol,'protocol_sha256':hashlib.sha256(PROTOCOL.read_bytes()).hexdigest(),
        'development':{},'selection':{},'audits':{},'source_sha256':{}}
    chosen_penalties={}
    for family in protocol['families']:
        options=[]
        for penalty in protocol['model_parameters']['linear_penalties'] if family.startswith('poisson_linear') else [1.]:
            folds=[]
            for spec in protocol['development_folds']:
                train=subset(data,spec['train']);valid=subset(data,spec['validate'])
                model=make_model(family,penalty).fit(train);pred=model.predict(valid);ratio=SeasonalRatio().fit(train).predict(valid)
                folds.append({'spec':spec,'full':diagnostics(valid,pred),'blends':{
                    str(w):diagnostics(valid,(1-w)*ratio+w*pred) for w in protocol['blend_weights']}})
            score=float(np.mean([f['full']['monthly_mae'] for f in folds]))
            options.append({'penalty':penalty,'mean_mae':score,'folds':folds})
            print('development',family,penalty,round(score,2),flush=True)
        best=min(options,key=lambda x:x['mean_mae']);chosen_penalties[family]=best['penalty'];report['development'][family]=options
        save('development.json',report)
    train=subset(data,protocol['training']);valid=subset(data,protocol['selection'])
    ratio=SeasonalRatio().fit(train);base=ratio.predict(valid);baseline=diagnostics(valid,base)
    report['baseline_selection']=baseline;report['chosen_penalties']=chosen_penalties
    models={};predictions={}
    for family in protocol['families']:
        model=make_model(family,chosen_penalties[family]).fit(train);pred=model.predict(valid);models[family]=model;predictions[family]=pred
        with (MDIR/f'{family}.pkl').open('wb') as h:pickle.dump(model,h)
        for weight in protocol['blend_weights']:
            name=f'{family}__w{weight}';s=diagnostics(valid,(1-weight)*base+weight*pred);s['gate']=gate(s,baseline)
            s['family']=family;s['weight']=weight;report['selection'][name]=s
            print('selection',name,round(s['monthly_mae'],2),s['gate'],flush=True)
    eligible={n:s for n,s in report['selection'].items() if all(s['gate'].values())}
    selected=min(eligible,key=lambda n:eligible[n]['monthly_mae']) if eligible else None
    report['selected_candidate']=selected
    # Save all choices before any new benchmark predictions are computed.
    save('selection.json',report)
    export=valid[['date','gy','gx','modis_count','viirs_count']].copy();export['baseline']=base
    for f,p in predictions.items():export[f]=p
    export.to_csv(OUT/'selection_predictions.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    if selected:
        winner=report['selection'][selected];family=winner['family'];weight=winner['weight'];model=models[family]
        for label,years in [('known_benchmark',protocol['known_benchmark']),('backward_audit',protocol['backward_audit'])]:
            f=subset(data,years);b=ratio.predict(f);p=(1-weight)*b+weight*model.predict(f)
            s=diagnostics(f,p);bs=diagnostics(f,b)
            report['audits'][label]={'candidate':s,'baseline':bs,'gate':gate(s,bs)}
            e=f[['date','gy','gx','modis_count','viirs_count']].copy();e['baseline']=b;e['candidate']=p
            e.to_csv(OUT/f'{label}_predictions.csv.gz',index=False,compression={'method':'gzip','mtime':0})
            print(label,'candidate',round(s['monthly_mae'],2),'baseline',round(bs['monthly_mae'],2),'gate',gate(s,bs),flush=True)
        with (MDIR/'candidate.pkl').open('wb') as h:pickle.dump({'model':model,'baseline':ratio,'weight':weight,'name':selected},h)
    for path in ['backend/harmonization_v4.py','scripts/prepare_harmonization_v4.py','scripts/train_harmonization_v4.py']:
        report['source_sha256'][path]=hashlib.sha256((ROOT/path).read_bytes()).hexdigest()
    report['production_changed']=False
    save('report.json',report)
    print('Selected',selected,flush=True)


if __name__=='__main__':run()
