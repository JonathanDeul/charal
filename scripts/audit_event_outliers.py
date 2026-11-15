#!/usr/bin/env python3
"""Known-case v2 audit and a frozen review sheet; no model selection here."""
from pathlib import Path
from datetime import date, timedelta
import csv
import hashlib
import json
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
import pandas as pd
from shapely.geometry import shape
from shapely import intersects_xy, prepare
from backend.app import event_scorer
from backend.anomalies import EPOCH
from backend.fire_events import project, RADIUS_KM

ANCHORS=['2014-01-18','2014-08-14','2017-09-01','2018-11-11','2020-09-15','2021-06-21','2025-01-10']


def main():
    out=ROOT/'data/research/event_outliers_v2';out.mkdir(parents=True,exist_ok=True)
    scorer=event_scorer();obs=scorer.obs
    protocol={'anchors':ANCHORS,'measurement_days':7,'season_days':30,'reference':'viirs','threshold':95,
              'tracking_km':3,'tracking_days':2,'comparison_radius_km':10,
              'review_selection':'Up to five lowest event IDs in each reason category per fixed anchor; human judgments are deliberately blank.',
              'status':'Known-case development audit, not an untouched benchmark or human validation.'}
    (out/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n')
    review=[];snapshots=[]
    for text in ANCHORS:
        r=scorer.score(date.fromisoformat(text))
        snapshots.append(r)
        groups={}
        for e in sorted(r['events'],key=lambda e:e['id']):
            category='first_recorded' if e['first_recorded'] else 'both' if len(e['reasons'])==2 else e['reasons'][0] if e['reasons'] else 'not_flagged'
            if groups.get(category,0)>=5:continue
            groups[category]=groups.get(category,0)+1
            review.append({'anchor':text,'event_id':e['id'],'label':e['label'],'category':category,
                           'occurrence_score':e['occurrence_score'],'activity_score':e['activity_score'],
                           'own_activity_10km':e['activity'],'reference_years':len(e['reference_years']),
                           'active_local_years':len(e['active_reference_years']),
                           'regional_activity_weight':e['regional_activity_weight'],
                           'human_event_identity':'','human_unusual_occurrence':'','human_unusual_activity':'','notes':''})
    (out/'snapshots.json').write_text(json.dumps(snapshots,separators=(',',':'),allow_nan=False)+'\n')
    with open(out/'review.csv','w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(review[0]));writer.writeheader();writer.writerows(review)

    previous=ROOT/'data/research/activity_outcomes/perimeter_associations.csv'
    rows=[]
    if previous.exists():
        old=pd.read_csv(previous)
        records={r['id']:r for r in json.loads((ROOT/'data/processed/perimeters.json').read_text())}
        for j,row in old.dropna(subset=['peak_week_score']).iterrows():
            record=records[row['id']];anchor=(date.fromisoformat(row['peak_week_anchor'])-EPOCH).days
            low,high=np.searchsorted(scorer.sorted_days,[anchor-3,anchor+4])
            idx=scorer.by_day[low:high];idx=idx[obs['sensor'][idx]==1]
            geom=shape(record['geometry']);prepare(geom)
            west,south,east,north=geom.bounds
            idx=idx[(obs['longitude'][idx]>=west)&(obs['longitude'][idx]<=east)&(obs['latitude'][idx]>=south)&(obs['latitude'][idx]<=north)]
            idx=idx[intersects_xy(geom,obs['longitude'][idx],obs['latitude'][idx])]
            # Apply the same source-event date support as the original audit.
            start=(date.fromisoformat(row['alarm_date'])-EPOCH).days
            end=(date.fromisoformat(row['containment_date'])-EPOCH).days
            idx=idx[(obs['day'][idx]>=start)&(obs['day'][idx]<=end)]
            if not len(idx):continue
            ids,counts=np.unique(scorer.tracks[idx],return_counts=True);track=int(ids[np.argmax(counts)])
            e=scorer.describe_event(track,anchor,7,30,'viirs',95)
            if e is None:continue
            center=project(np.array([e['latitude']]),np.array([e['longitude']]))[0]
            linked=idx[(scorer.tracks[idx]==track)&(np.linalg.norm(scorer.xy[idx]-center,axis=1)<=RADIUS_KM)]
            rows.append({'id':row['id'],'name':row['name'],'year':int(row['year']),'area_ha':float(row['area_ha']),
                         'anchor':row['peak_week_anchor'],'track':track,
                         'old_context_activity':float(row['peak_week_context_activity']),
                         'old_linked_reports':int(row['peak_week_fire_reports_in_cell']),
                         'old_score':float(row['peak_week_score']),
                         'new_own_activity':e['activity'],'new_linked_reports':int(len(linked)),
                         'occurrence_score':e['occurrence_score'],'activity_score':e['activity_score'],
                         'first_recorded':e['first_recorded'],'outlier':e['outlier'],
                         'active_local_years':len(e['active_reference_years']),
                         'regional_activity_weight':e['regional_activity_weight']})
            if j%300==0:print(f'Perimeter comparison {j}',flush=True)
    if rows:
        with open(out/'perimeter_comparison.csv','w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    summary={'protocol':protocol,'review_rows':len(review),'snapshots':[
        {key:r[key] for key in ['anchor_date','events_total','outlier_events','first_recorded_events']} for r in snapshots],
        'first_recorded_preserved':all(e['outlier'] and e['occurrence_score']==100 for r in snapshots for e in r['events'] if e['first_recorded']),
        'perimeter_comparisons':len(rows)}
    summary['input_sha256']={name:hashlib.sha256((ROOT/'data/processed'/name).read_bytes()).hexdigest()
                             for name in ['activity_events.npz','activity_events.json','observations.npz','activity_daily.npz']}
    small=[r for r in rows if r['area_ha']<100 and r['old_score']>=95]
    if small:
        positive=[r for r in small if r['new_linked_reports']>0]
        summary['previously_flagged_small_events']={'n':len(small),'with_linked_reports_in_new_support':len(positive),
            'old_median_linked_share':float(np.median([r['old_linked_reports']/r['old_context_activity'] for r in small])),
            'new_median_linked_share':float(np.median([r['new_linked_reports']/r['new_own_activity'] for r in positive])),
            'new_fraction_share_below_half':float(np.mean([r['new_linked_reports']/r['new_own_activity']<.5 for r in positive])),
            'new_outliers':sum(r['outlier'] for r in small)}
    (out/'summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
    print(json.dumps(summary,indent=2),flush=True)


if __name__=='__main__':main()
