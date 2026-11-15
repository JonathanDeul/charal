#!/usr/bin/env python3
"""Residual calibration and complete-year-block refit variability for release."""
import os
os.environ.setdefault('OMP_NUM_THREADS','4');os.environ.setdefault('OPENBLAS_NUM_THREADS','4')
from pathlib import Path
import argparse,json,pickle,sys,hashlib
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend.historical_transfer import HistoricalTransfer
from backend.harmonization_v2 import SeasonalRatio
from backend.harmonization_v4 import make_model
from backend.harmonization_uncertainty import fit_bands,evaluate_bands,aggregate
from scripts.train_harmonization_v2 import subset
OUT=ROOT/'data/research/harmonization_release';MDIR=ROOT/'models/harmonization_release'


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--bootstrap',type=int,default=39);args=parser.parse_args()
    if args.bootstrap<20:raise ValueError('At least20 refits required for descriptive bootstrap range')
    report=json.loads((OUT/'report.json').read_text())
    if not report['all_gates_passed']:raise ValueError('Cannot prepare failed candidate')
    data=pd.read_csv(ROOT/'data/research/harmonization_v4/cells.csv.gz',dtype={'ecoregion':str})
    model=HistoricalTransfer.from_research(ROOT)
    cal=subset(data,[2021,2022]);pred=model.predict(cal);bands=fit_bands(cal,pred,levels=(.8,.95),scale_power=.5)
    uncertainty={'residual_calibration':bands,'assessment':{},'bootstrap':{},'limitations':[
        'Residual bands measure reference-scale disagreement, not true fire activity.',
        'Previously inspected calibration years and temporal/spatial dependence prevent nominal coverage guarantees.',
        'Bootstrap refits measure training-year variation of this frozen mixture; they do not quantify all selection uncertainty or historical sensor/algorithm bias.',
        'Before Aqua operation the deployed baseline fallback is retained; historic residual-band coverage is unvalidated.',
        'Bootstrap percentile ranges are separate from predictive residual bands; neither is an interval for burned area or true fire count.']}
    for label,years in [('calibration',[2021,2022]),('known_benchmark',[2023,2025]),('backward',[2012,2012])]:
        f=subset(data,years);uncertainty['assessment'][label]=evaluate_bands(f,model.predict(f),bands)
    train=subset(data,[2013,2020]);blocks=[[2013,2014],[2015,2016],[2017,2018],[2019,2020]]
    rng=np.random.default_rng(497);samples=[];draws=[]
    cache=OUT/'bootstrap_predictions.npz'
    for i in range(args.bootstrap):
        selected=rng.integers(0,len(blocks),size=len(blocks));years=[year for b in selected for year in blocks[b]]
        boot=pd.concat([train[train.year.eq(year)] for year in years],ignore_index=True)
        baseline=SeasonalRatio().fit(boot);learned=make_model('hurdle_rich').fit(boot)
        fitted=HistoricalTransfer(baseline,learned,report['choice']);prediction=fitted.predict(data)
        samples.append(prediction.astype(np.float32));draws.append(years)
        print('Bootstrap',i+1,'/',args.bootstrap,flush=True)
    samples=np.array(samples);np.savez_compressed(cache,prediction=samples)
    # Aggregate each refit first: local quantiles cannot be added into a region.
    dates=sorted(data.date.unique());regional={}
    for name,mask in [('state',np.ones(len(data),bool)),('north',data.latitude.to_numpy()>=39.5),('south',data.latitude.to_numpy()<39.5)]:
        arrays=[]
        for pred in samples:
            g=pd.DataFrame({'date':data.loc[mask,'date'].to_numpy(),'prediction':pred[mask]}).groupby('date').prediction.sum().reindex(dates)
            arrays.append(g.to_numpy())
        values=np.array(arrays);regional[name]=[{'date':date,'lower90':float(lo),'median':float(med),'upper90':float(hi)} for date,lo,med,hi in zip(dates,*np.quantile(values,[.05,.5,.95],axis=0))]
    uncertainty['bootstrap']={'method':'Resample four complete two-year blocks with replacement, refit ratio and learned expert, freeze mixture weights',
        'refits':args.bootstrap,'seed':497,'year_draws':draws,'percentiles':[.05,.5,.95],
        'interpretation':'Descriptive training-data variability range, not calibrated historical predictive coverage. Model-family/mixture selection is not rerun.',
        'regions':regional,'cache_sha256':hashlib.sha256(cache.read_bytes()).hexdigest()}
    (OUT/'uncertainty.json').write_text(json.dumps(uncertainty,indent=2,allow_nan=False))
    with (MDIR/'candidate.pkl').open('wb') as f:pickle.dump({'model':model,'uncertainty':bands,'report_sha256':hashlib.sha256((OUT/'report.json').read_bytes()).hexdigest()},f)
    print('Prepared release candidate and uncertainty')


if __name__=='__main__':main()
