#!/usr/bin/env python3
"""Preserve sensor/day-night information lost by pooled MODIS summaries."""
from pathlib import Path
import hashlib,json,sys
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend.science import eligible_hotspots
OUT=ROOT/'data/research/harmonization_platforms'


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    data=pd.read_csv(ROOT/'data/research/harmonization_v4/cells.csv.gz',dtype={'ecoregion':str})
    raw=pd.read_csv(ROOT/'data/processed/hotspots.csv',dtype={'confidence':str,'acq_time':str})
    raw,_=eligible_hotspots(raw);raw=raw[raw.sensor.eq('MODIS')].copy()
    raw['date']=raw.acq_date.str[:7]+'-01';raw['gy']=np.floor(raw.latitude*2).astype(int);raw['gx']=np.floor(raw.longitude*2).astype(int)
    raw['contrast']=raw.brightness-raw.bright_t31;raw['footprint']=raw.scan*raw.track
    raw['confidence_numeric']=pd.to_numeric(raw.confidence);raw['day']=raw.daynight.eq('D').astype(float)
    raw['platform']=raw.satellite.str.upper().map({'TERRA':'terra','T':'terra','AQUA':'aqua','A':'aqua'})
    if raw.platform.isna().any():raise ValueError('Unknown platform')
    hour=pd.to_numeric(raw.acq_time.str.zfill(4).str[:2])+pd.to_numeric(raw.acq_time.str.zfill(4).str[2:])/60
    raw['solar_hour']=(hour+raw.longitude/15)%24
    raw['solar_sin']=np.sin(raw.solar_hour*2*np.pi/24);raw['solar_cos']=np.cos(raw.solar_hour*2*np.pi/24)
    rows=[]
    for keys,f in raw.groupby(['date','gy','gx','platform']):
        date,gy,gx,p=keys
        occupied=set(zip(np.floor(f.latitude*20).astype(int),np.floor(f.longitude*20).astype(int)))
        r={'date':date,'gy':gy,'gx':gx,'platform':p,'n':len(f),'frp_mean':float(f.frp.mean()),'frp_sum':float(f.frp.sum()),
            'frp_q25':float(f.frp.quantile(.25)),'frp_q90':float(f.frp.quantile(.9)),'footprint_mean':float(f.footprint.mean()),
            'contrast_mean':float(f.contrast.mean()),'confidence_mean':float(f.confidence_numeric.mean()),
            'day_fraction':float(f.day.mean()),'detection_days':f.acq_date.nunique(),'occupancy':len(occupied),
            'solar_sin':float(f.solar_sin.mean()),'solar_cos':float(f.solar_cos.mean())}
        for label,mask in [('day',f.daynight.eq('D')),('night',f.daynight.eq('N'))]:
            a=f[mask];r[label+'_n']=len(a);r[label+'_frp_mean']=float(a.frp.mean()) if len(a) else 0
            r[label+'_contrast_mean']=float(a.contrast.mean()) if len(a) else 0
            r[label+'_footprint_mean']=float(a.footprint.mean()) if len(a) else 0
        rows.append(r)
    desc=pd.DataFrame(rows);cols=[c for c in desc if c not in ['date','gy','gx','platform']]
    for p in ['terra','aqua']:
        block=desc[desc.platform.eq(p)].drop(columns='platform').rename(columns={c:f'{p}_{c}' for c in cols})
        data=data.merge(block,on=['date','gy','gx'],how='left',validate='one_to_one')
    added=[p+'_'+c for p in ['terra','aqua'] for c in cols]
    data[added]=data[added].fillna(0)
    np.testing.assert_array_equal(data.terra_n+data.aqua_n,data.modis_count)
    np.testing.assert_array_equal(data.terra_day_n+data.terra_night_n,data.terra_n)
    np.testing.assert_array_equal(data.aqua_day_n+data.aqua_night_n,data.aqua_n)
    data.to_csv(OUT/'cells.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    manifest={'features':added,'source':'Existing California standard-processing MODIS archive, same eligibility rule',
        'source_sha256':hashlib.sha256((ROOT/'data/processed/hotspots.csv').read_bytes()).hexdigest(),
        'cells_sha256':hashlib.sha256((OUT/'cells.csv.gz').read_bytes()).hexdigest(),
        'count_partition_verified':True,'limitations':['Detection-only descriptors, not observation exposure.','Approximate local solar time from UTC+longitude/15, not a measured orbital crossing time.']}
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2));print('Saved',len(added),'platform-specific features')


if __name__=='__main__':main()
