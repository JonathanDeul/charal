#!/usr/bin/env python3
"""Prepare deterministic activity tracks and retrospective CAL FIRE overlaps."""
from pathlib import Path
from datetime import date, datetime, timezone
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
from shapely.geometry import shape
from shapely import intersects_xy, prepare
from backend.fire_events import cluster_detections, project
from backend.anomalies import EPOCH


def main():
    folder = ROOT/'data/processed'
    with np.load(folder/'observations.npz',allow_pickle=False) as f:obs={k:f[k] for k in f.files}
    xy=project(obs['latitude'].astype(float),obs['longitude'].astype(float))
    tracks=cluster_detections(obs['day'],obs['sensor'],xy)
    np.savez_compressed(folder/'activity_events.npz',tracks=tracks.astype(np.int32))
    metadata={str(int(track)):{'associations':[]} for track in np.unique(tracks)}
    order=np.argsort(obs['day'],kind='stable');days=obs['day'][order]
    records=json.loads((folder/'perimeters.json').read_text())
    for row in records:
        if not row.get('alarm_date_ms') or not row.get('containment_date_ms'):continue
        start=datetime.fromtimestamp(row['alarm_date_ms']/1000,tz=timezone.utc).date()
        end=datetime.fromtimestamp(row['containment_date_ms']/1000,tz=timezone.utc).date()
        if not date(2001,1,1)<=start<=end<=date(2025,12,31) or (end-start).days>365:continue
        low,high=np.searchsorted(days,[(start-EPOCH).days,(end-EPOCH).days+1])
        idx=order[low:high]
        geom=shape(row['geometry'])
        if not geom.is_valid:continue
        west,south,east,north=geom.bounds
        idx=idx[(obs['longitude'][idx]>=west)&(obs['longitude'][idx]<=east)&(obs['latitude'][idx]>=south)&(obs['latitude'][idx]<=north)]
        prepare(geom)
        idx=idx[intersects_xy(geom,obs['longitude'][idx],obs['latitude'][idx])]
        ids,counts=np.unique(tracks[idx],return_counts=True)
        for track,count in zip(ids,counts):
            metadata[str(int(track))]['associations'].append({'id':row['id'],'name':row['name'],'year':row['year'],'observations':int(count)})
    for row in metadata.values():row['associations'].sort(key=lambda r:(-r['observations'],r['id']))
    result={'schema_version':1,'events':metadata,'source_sha256':hashlib.sha256((folder/'observations.npz').read_bytes()).hexdigest(),
            'tracks_sha256':hashlib.sha256((folder/'activity_events.npz').read_bytes()).hexdigest(),
            'perimeters_sha256':hashlib.sha256((folder/'perimeters.json').read_bytes()).hexdigest(),
            'tracking':'Same-sensor 1 km occupied cells connected within 3 km and two UTC days. These are inferred activity tracks, not verified incident identities.'}
    (folder/'activity_events.json').write_text(json.dumps(result,separators=(',',':'))+'\n')
    print(json.dumps({'tracks':len(metadata),'tracks_with_cal_fire_overlap':sum(bool(r['associations']) for r in metadata.values()),'observations':len(tracks)}))


if __name__=='__main__':main()
