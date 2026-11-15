#!/usr/bin/env python3
"""Build finer spatial and temporal MODIS-only monthly descriptors."""
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
from scipy import ndimage

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend.science import eligible_hotspots
OUT=ROOT/'data/research/harmonization_v4'


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    frame=pd.read_csv(ROOT/'data/research/harmonization_v2/cells.csv.gz',dtype={'ecoregion':str})
    frame=frame[frame.state.eq('CA')].copy()
    raw=pd.read_csv(ROOT/'data/processed/hotspots.csv',dtype={'confidence':str,'acq_time':str})
    raw,_=eligible_hotspots(raw);raw=raw[raw.sensor.eq('MODIS')].copy()
    raw['date']=raw.acq_date.str[:7]+'-01';raw['gy']=np.floor(raw.latitude*2).astype(int);raw['gx']=np.floor(raw.longitude*2).astype(int)
    raw['contrast']=raw.brightness-raw.bright_t31
    rows=[]
    for (date,gy,gx),f in raw.groupby(['date','gy','gx']):
        occupancy=np.zeros((10,10),bool)
        y=np.clip(np.floor((f.latitude.to_numpy()-gy/2)*20).astype(int),0,9)
        x=np.clip(np.floor((f.longitude.to_numpy()-gx/2)*20).astype(int),0,9)
        occupancy[y,x]=True
        labels,n=ndimage.label(occupancy,structure=np.ones((3,3)))
        sizes=np.bincount(labels.ravel())[1:]
        daily=f.groupby('acq_date').size().to_numpy()
        rows.append({'date':date,'gy':gy,'gx':gx,'subcell_occupancy':int(occupancy.sum()),
            'spatial_components':n,'largest_component':int(sizes.max()),'largest_component_fraction':float(sizes.max()/occupancy.sum()),
            'frp_q25':float(f.frp.quantile(.25)),'frp_q50':float(f.frp.quantile(.5)),'frp_q90':float(f.frp.quantile(.9)),
            'contrast_mean':float(f.contrast.mean()),'contrast_max':float(f.contrast.max()),
            'confidence_mean':float(pd.to_numeric(f.confidence).mean()),
            'daily_max':int(daily.max()),'daily_concentration':float(np.sum(daily**2)/daily.sum()**2),
            'reports_per_occupied_subcell':len(f)/occupancy.sum()})
    frame=frame.merge(pd.DataFrame(rows),on=['date','gy','gx'],how='left',validate='one_to_one')
    newcols=list(rows[0].keys())[3:]
    frame[newcols]=frame[newcols].fillna(0)
    # All neighbors are MODIS source observations, including the target month;
    # zero padding denotes absent neighboring grid support, not clear-sky exposure.
    coords=frame[['gy','gx']].drop_duplicates().sort_values(['gy','gx'])
    loc=coords.to_numpy();distance=np.max(np.abs(loc[:,None,:]-loc[None,:,:]),axis=2)
    for radius in [1,2]:
        weights=((distance<=radius)&(distance>0)).astype(float)
        for source in ['modis_count','frp_sum']:
            pivot=frame.pivot(index='date',columns=['gy','gx'],values=source).reindex(columns=pd.MultiIndex.from_frame(coords))
            values=pivot.to_numpy()@weights.T
            addition=pd.DataFrame(values,index=pivot.index,columns=pivot.columns).stack([0,1],future_stack=True).rename(f'neighbor{radius}_{source}').reset_index()
            frame=frame.merge(addition,on=['date','gy','gx'],how='left',validate='one_to_one')
    # No lagged VIIRS is allowed. Within-cell recent MODIS history is available
    # historically; no future month or cross-split temporal input is needed.
    frame=frame.sort_values(['gy','gx','date'])
    for source in ['modis_count','frp_sum']:
        frame[f'previous_{source}']=frame.groupby(['gy','gx'])[source].shift(1).fillna(0)
        frame[f'previous3_{source}']=frame.groupby(['gy','gx'])[source].transform(lambda s:s.shift(1).rolling(3,min_periods=1).mean()).fillna(0)
    frame.to_csv(OUT/'cells.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    sources=['data/research/harmonization_v2/cells.csv.gz','data/processed/hotspots.csv']
    (OUT/'manifest.json').write_text(json.dumps({'rows':len(frame),'features_added':newcols+['neighbor1_modis_count','neighbor2_modis_count','neighbor1_frp_sum','neighbor2_frp_sum','previous_modis_count','previous3_modis_count','previous_frp_sum','previous3_frp_sum'],
        'input_sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sources},
        'cells_sha256':hashlib.sha256((OUT/'cells.csv.gz').read_bytes()).hexdigest()},indent=2))
    print('Saved',len(frame),'monthly rows',flush=True)


if __name__=='__main__':main()
