#!/usr/bin/env python3
"""Post-selection checks of the frozen v4 winner; no retuning or reselection."""
import os
os.environ.setdefault('OMP_NUM_THREADS','4');os.environ.setdefault('OPENBLAS_NUM_THREADS','4')
from pathlib import Path
import json
import pickle
import sys
import hashlib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier,HistGradientBoostingRegressor

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend.harmonization_v2 import SeasonalRatio,NUMERIC
from backend.harmonization_v4 import make_model,features,RICH
from backend.harmonization_v3 import DailyData
from scripts.train_harmonization_v2 import subset,diagnostics
OUT=ROOT/'data/research/harmonization_v4'


def save(name,obj):(OUT/name).write_text(json.dumps(obj,indent=2,allow_nan=False))


def group_scores(f,p):
    error=p-f.viirs_count.to_numpy()
    def calc(mask):
        e=error[mask];y=f.viirs_count.to_numpy()[mask];pr=p[mask]
        return {'n':int(mask.sum()),'mae':float(np.abs(e).mean()),'bias_total':float(e.sum()),
            'reference_total':float(y.sum()),'predicted_total':float(pr.sum()),
            'bias_fraction':float(e.sum()/y.sum()) if y.sum() else None} if mask.any() else None
    return {label:calc(mask.to_numpy()) for label,mask in {
        'both_zero':f.modis_count.eq(0)&f.viirs_count.eq(0),'viirs_only':f.modis_count.eq(0)&f.viirs_count.gt(0),
        'all_zero_modis':f.modis_count.eq(0),'positive_modis':f.modis_count.gt(0),'high_activity':f.modis_count.ge(500)}.items()}


def ablation(train,valid,columns):
    ratio=SeasonalRatio().fit(train)
    x=features(train)[:,columns];v=features(valid)[:,columns];y=train.viirs_count.to_numpy()
    e=ratio.predict(train)+.05
    kw=dict(max_iter=120,learning_rate=.035,max_leaf_nodes=7,min_samples_leaf=100,l2_regularization=10,early_stopping=False,random_state=42)
    classifier=HistGradientBoostingClassifier(**kw).fit(x,y>0)
    reg=HistGradientBoostingRegressor(loss='poisson',**kw).fit(x[y>0],y[y>0]/e[y>0],sample_weight=e[y>0])
    return (ratio.predict(valid)+.05)*classifier.predict_proba(v)[:,1]*reg.predict(v)


def main():
    report=json.loads((OUT/'report.json').read_text());selected=report['selected_candidate']
    if not selected:raise ValueError('No selected candidate to audit')
    chosen=report['selection'][selected];family=chosen['family'];weight=chosen['weight'];penalty=report['chosen_penalties'][family]
    data=pd.read_csv(OUT/'cells.csv.gz',dtype={'ecoregion':str});train=subset(data,[2013,2020]);valid=subset(data,[2021,2022])
    with (ROOT/'models/harmonization_v4/candidate.pkl').open('rb') as h:fitted=pickle.load(h)
    model,baseline=fitted['model'],fitted['baseline']
    audit={'selection_unchanged':selected,'limits':['Post-selection diagnostics, not an additional selection pass.',
        'CAL FIRE linkage/geometry does not establish independent fires. Historical evaluation periods are already known.'],'strata':{},'ablations':{}}
    for label,years in [('selection',[2021,2022]),('known_benchmark',[2023,2025]),('backward_audit',[2012,2012])]:
        f=subset(data,years);b=baseline.predict(f);p=(1-weight)*b+weight*model.predict(f)
        audit['strata'][label]={'candidate':group_scores(f,p),'baseline':group_scores(f,b)}
    # Geographic buffer includes both models' 1-degree source neighborhoods.
    north=subset(data,[2023,2025]);north=north[north.latitude>=39.5]
    loc=train[['latitude','longitude']].to_numpy();ref=north[['latitude','longitude']].drop_duplicates().to_numpy()
    distance=np.max(np.abs(loc[:,None,:]-ref[None,:,:]),axis=2).min(axis=1)
    south=train[distance>2]
    spatial=make_model(family,penalty).fit(south);sr=SeasonalRatio().fit(south)
    sb=sr.predict(north);sp=(1-weight)*sb+weight*spatial.predict(north)
    audit['spatial']={'training_rows':len(south),'minimum_center_distance':float(distance[distance>2].min()),
        'candidate':diagnostics(north,sp),'baseline':diagnostics(north,sb)}
    print('spatial',audit['spatial']['candidate']['monthly_mae'],audit['spatial']['baseline']['monthly_mae'],flush=True)
    save('audit.json',audit)
    # Drop an entire training cell-month if any daily support was event-purged.
    daily=DailyData(ROOT);idx,guard=daily.indices([2013,2020],[[2021,2022],[2023,2025]])
    kept=daily.frame(idx).groupby(['month','gy','gx']).size().rename('kept_days').reset_index()
    kept['date']=kept['month']+'-01'
    guarded=train.merge(kept[['date','gy','gx','kept_days']],on=['date','gy','gx'],how='left',validate='one_to_one')
    guarded=guarded[guarded.kept_days.eq(pd.to_datetime(guarded.date).dt.days_in_month)]
    gm=make_model(family,penalty).fit(guarded);gb=SeasonalRatio().fit(guarded)
    audit['guarded_sensitivity']={'training_rows':len(guarded),'removed_cell_months':len(train)-len(guarded),'crossing_groups':len(guard['crossing_groups'])}
    for label,years in [('selection',[2021,2022]),('known_benchmark',[2023,2025])]:
        f=subset(data,years);b=gb.predict(f);p=(1-weight)*b+weight*gm.predict(f)
        audit['guarded_sensitivity'][label]={'candidate':diagnostics(f,p),'baseline':diagnostics(f,b)}
        print('guarded',label,audit['guarded_sensitivity'][label]['candidate']['monthly_mae'],audit['guarded_sensitivity'][label]['baseline']['monthly_mae'],flush=True)
    save('audit.json',audit)
    if family=='hurdle_rich':
        original=len(NUMERIC)+4;allcols=list(range(original+len(RICH)))
        spatial_cols=[original+i for i,c in enumerate(RICH) if not c.startswith(('neighbor','previous'))]
        context_cols=[original+i for i,c in enumerate(RICH) if c.startswith(('neighbor','previous'))]
        for label,cols in [('original_only',list(range(original))),('original_plus_fine',list(range(original))+spatial_cols),
            ('original_plus_context',list(range(original))+context_cols)]:
            p=ablation(train,valid,cols);audit['ablations'][label]=diagnostics(valid,p)
            print('ablation',label,audit['ablations'][label]['monthly_mae'],flush=True)
        audit['ablations']['full']=report['selection'][selected]
    audit['source_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    save('audit.json',audit)
    print('Audit complete; no reselection',flush=True)


if __name__=='__main__':main()
