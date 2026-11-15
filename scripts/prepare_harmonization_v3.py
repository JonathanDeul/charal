#!/usr/bin/env python3
"""Prepare dense daily MODIS context and CA-only labels from cached sources."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
from shapely import intersects_xy
from shapely.geometry import shape, box
from shapely.ops import unary_union

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.science import eligible_hotspots
OUT=ROOT/'data/research/harmonization_v3'


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    grid=pd.read_csv(ROOT/'data/research/harmonization_v2/grid.csv',dtype={'ecoregion':str})
    grid=grid[grid.state.eq('CA')].reset_index(drop=True)
    gy0,gx0=int(grid.gy.min())-2,int(grid.gx.min())-2
    H,W=int(grid.gy.max())-gy0+3,int(grid.gx.max())-gx0+3
    dates=pd.date_range('2012-01-01','2025-12-31'); T=len(dates)
    context=np.zeros((T,H,W,4),np.float32)
    local=np.zeros((T,len(grid),4),np.float32)
    target=np.zeros((T,len(grid)),np.float32)
    geometry=json.loads((ROOT/'data/research/harmonization_v2/geography.json').read_text())
    domain=unary_union([shape(f['geometry']) for s in geometry['states'].values() for f in s['features']]).buffer(0)
    support=np.array([[domain.intersects(box((gx0+x)/2,(gy0+y)/2,(gx0+x+1)/2,(gy0+y+1)/2)) for x in range(W)] for y in range(H)])
    sources=[]
    for year in range(2012,2026):
        path=ROOT/f'data/raw/modis_{year}_United_States.csv.gz'
        for f in pd.read_csv(path,chunksize=200_000,dtype={'acq_time':str,'confidence':str}):
            f=f[f.latitude.between(gy0/2,(gy0+H)/2,inclusive='left')&f.longitude.between(gx0/2,(gx0+W)/2,inclusive='left')].copy()
            f['sensor']='MODIS';f,_=eligible_hotspots(f)
            f=f[intersects_xy(domain,f.longitude.to_numpy(),f.latitude.to_numpy())].drop_duplicates(['latitude','longitude','acq_date','acq_time','satellite','frp'])
            t=(pd.to_datetime(f.acq_date)-dates[0]).dt.days.to_numpy()
            y=np.floor(f.latitude.to_numpy()*2).astype(int)-gy0;x=np.floor(f.longitude.to_numpy()*2).astype(int)-gx0
            terra=f.satellite.str.upper().isin(['TERRA','T']).to_numpy()
            aqua=f.satellite.str.upper().isin(['AQUA','A']).to_numpy()
            if not (terra|aqua).all():raise ValueError('Unknown MODIS platform')
            for c,v in enumerate([terra,aqua,f.frp.to_numpy(),f.daynight.eq('D').to_numpy()]):np.add.at(context[:,:,:,c],(t,y,x),v.astype(np.float32))
        sources.append({'path':str(path.relative_to(ROOT)),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
        print('MODIS context',year,flush=True)
    ca=pd.read_csv(ROOT/'data/processed/hotspots.csv',dtype={'acq_time':str,'confidence':str})
    ca,_=eligible_hotspots(ca);ca=ca[pd.to_datetime(ca.acq_date).ge(dates[0])]
    ids={(int(r.gy),int(r.gx)):i for i,r in grid.iterrows()}
    t=(pd.to_datetime(ca.acq_date)-dates[0]).dt.days.to_numpy()
    cell=np.array([ids.get((int(y),int(x)),-1) for y,x in zip(np.floor(ca.latitude*2),np.floor(ca.longitude*2))])
    if (cell<0).any():raise ValueError('CA detection outside fixed grid')
    m=ca.sensor.eq('MODIS').to_numpy();v=ca.sensor.eq('VIIRS').to_numpy()
    if not ca.loc[v,'satellite'].str.upper().isin(['N','SNPP','NPP','S-NPP','SUOMI-NPP']).all():raise ValueError('Not SNPP')
    np.add.at(target,(t[v],cell[v]),1)
    for c,values in enumerate([ca.satellite.str.upper().isin(['TERRA','T']),ca.satellite.str.upper().isin(['AQUA','A']),ca.frp,ca.daynight.eq('D')]):
        np.add.at(local[:,:,c],(t[m],cell[m]),np.asarray(values)[m].astype(np.float32))
    coverage=json.loads((ROOT/'data/processed/coverage.json').read_text())
    validmonth={r['date']:r['modis_missing_day_count']==0 and r['viirs_missing_day_count']==0 for r in coverage['monthly']}
    pair=np.array([validmonth[d.strftime('%Y-%m')] and d>=pd.Timestamp('2012-02-01') for d in dates])
    modis_missing={d for r in coverage['monthly'] for d in r['modis_missing_days']}
    context_day_valid=np.array([d.strftime('%Y-%m-%d') not in modis_missing for d in dates])
    np.savez_compressed(OUT/'daily.npz',context=context,local=local,target=target,support=support,
        date=dates.strftime('%Y-%m-%d').to_numpy(dtype='U10'),pair_complete=pair,context_day_valid=context_day_valid,
        gy0=gy0,gx0=gx0,grid_y=grid.gy.to_numpy()-gy0,grid_x=grid.gx.to_numpy()-gx0)
    grid.to_csv(OUT/'grid.csv',index=False)
    # Check all paired-month targets and central inputs against v2 before fitting.
    old=pd.read_csv(ROOT/'data/research/harmonization_v2/cells.csv.gz')
    old=old[old.state.eq('CA')&old.year.ge(2012)]
    for dt in pd.period_range('2012-02','2025-12',freq='M'):
        sel=dates.to_period('M')==dt; previous=old[old.date.eq(str(dt)+'-01')]
        assert int(target[sel].sum())==int(previous.viirs_count.sum())
        assert int(local[sel,:,:2].sum())==int(previous.modis_count.sum())
    manifest={'sources':sources,'channels':['Terra count','Aqua count','FRP sum MW','daytime count'],
        'shape':list(context.shape),'ca_cells':len(grid),'daily_ca_rows':int(target.size),
        'daily_sha256':hashlib.sha256((OUT/'daily.npz').read_bytes()).hexdigest(),
        'target_source_sha256':hashlib.sha256((ROOT/'data/processed/hotspots.csv').read_bytes()).hexdigest(),
        'monthly_parity_with_v2':'passed for every full reference month 2012-02 through 2025-12',
        'limitations':['Availability channel measures source/split support, not overpass/cloud exposure.','Context outside the five-state union is unavailable.','Monthly outage exclusions are conservative and shared with v2.']}
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2))
    print('Prepared',target.size,'daily CA rows',flush=True)


if __name__=='__main__':main()
