"""Event identity, exact support, two-part interpretation and preserved novelty."""
from datetime import date
import json
import hashlib
import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend.anomalies import EPOCH, END, calendar_axis
from backend.fire_events import (EventScorer, cluster_detections, window_event_max,
                                  two_part, combine_strength, inverse_project, project)
import backend.app as api


def day(text):return (date.fromisoformat(text)-EPOCH).days


def make_scorer(rows):
    """rows: date, inferred track, local x displacement (km), repetitions."""
    xy0=project(np.array([38.25]),np.array([-120.25]))[0]
    days,tracks,lat,lon=[],[],[],[]
    for text,track,dx,count in rows:
        y,x=inverse_project(xy0[0]+dx,xy0[1])
        days.extend([day(text)]*count);tracks.extend([track]*count)
        lat.extend([y]*count);lon.extend([x]*count)
    n=(END-EPOCH).days+1;years,season=calendar_axis(n)
    obs={'day':np.array(days),'sensor':np.ones(len(days),dtype=int),
         'latitude':np.array(lat),'longitude':np.array(lon)}
    valid=np.arange(n)>=day('2012-01-20')
    activity={'years':years,'season':season,'ratios':np.ones(366)*3,
              'viirs_valid':valid,'modis_valid':np.ones(n,dtype=bool)}
    return EventScorer(obs,activity,np.array(tracks),{})


def test_tracking_keeps_singletons_separates_sensors_and_long_gaps():
    d=np.array([1,3,6,1,1]);s=np.array([1,1,1,0,1])
    xy=np.array([[0.,0.],[2.,0.],[2.,0.],[0.,0.],[10.,0.]])
    ids=cluster_detections(d,s,xy)
    assert ids[0]==ids[1]
    assert len(set(ids))==4
    reverse=cluster_detections(d[::-1],s[::-1],xy[::-1])[::-1]
    assert np.array_equal(ids,reverse)


def test_reference_uses_single_events_not_neighbor_sum():
    result=window_event_max(np.array([10,10,11]),np.array([1,2,1]),np.array([2.,100.,3.]),30,3)
    assert result[10]==100  # Not 105.
    assert result[12]==3


def test_first_occurrence_is_outlier_without_any_positive_reference():
    c=two_part(np.zeros(20),np.ones(20),np.repeat([2013,2014],10),1)
    assert c['occurrence_score']==100 and c['no_seasonal_activity']
    assert c['activity_score_local'] is None


def test_first_recorded_is_preserved_even_with_later_activity():
    c=two_part(np.array([0.,1.,100.]),np.ones(3),np.array([2018,2021,2022]),2,first_recorded=True)
    assert c['occurrence_score']==100
    assert c['seasonal_zero_percent']==pytest.approx(100/3)
    strength,mix=combine_strength(c,[dict(activity_score_local=0.)])
    assert mix>0 and strength<c['activity_score_local']
    assert c['occurrence_score']==100


def test_conditional_strength_excludes_zero_windows_and_handles_ties():
    c=two_part(np.array([0.,0.,5.,5.,10.]),np.ones(5),np.array([2013]*5),5)
    assert c['occurrence_score']==40
    assert c['activity_score_local']==pytest.approx(100/3)


def test_event_does_not_inherit_nearby_large_fire():
    rows=[(f'{y}-11-30',y,0.,300) for y in range(2013,2025)]
    rows += [('2025-11-30',1,0.,1),('2025-11-30',2,5.,1000)]
    scorer=make_scorer(rows)
    r=scorer.score(date(2025,11,30))
    small=next(e for e in r['events'] if e['id']==1)
    large=next(e for e in r['events'] if e['id']==2)
    assert small['activity']==1 and not small['outlier']
    assert large['activity']==1000 and large['outlier']
    assert large['activity_score']==100


def test_archive_novelty_survives_short_history_and_regional_pooling():
    rows=[('2020-11-30',1,0.,2)]
    rows += [(f'{y}-11-30',y,30.,100) for y in range(2013,2026) if y!=2020]
    rows += [(f'{y}-11-30',y+100,0.,100) for y in range(2021,2026)]
    r=make_scorer(rows).score(date(2020,11,30))
    e=next(x for x in r['events'] if x['id']==1)
    assert e['occurrence_score']==100 and e['first_recorded'] and e['outlier']
    assert e['activity_score']<95
    assert e['regional_activity_weight']>=0
    assert 'first_recorded_activity' in e['reasons']
    json.dumps(r,allow_nan=False)


def test_no_positive_history_stays_flagged_when_strength_unknown():
    e=make_scorer([('2020-11-30',1,0.,1)]).score(date(2020,11,30))['events'][0]
    assert e['occurrence_score']==100 and e['outlier']
    assert e['activity_score'] is None and e['support']=='limited'


def test_regional_positive_reference_never_suppresses_local_novelty():
    rows=[('2020-11-30',1,0.,1)]
    rows += [(f'{year}-11-30',year,30.,100) for year in range(2013,2026) if year!=2020]
    e=next(e for e in make_scorer(rows).score(date(2020,11,30))['events'] if e['id']==1)
    assert e['regional_activity_weight']==1 and e['activity_score']==0
    assert e['occurrence_score']==100 and e['outlier'] and e['first_recorded']


def test_novelty_remains_outlier_even_without_ten_reference_years():
    scorer=make_scorer([('2020-11-30',1,0.,1)])
    scorer.activity['viirs_valid'][:]=False
    scorer.activity['viirs_valid'][day('2020-11-27'):day('2020-12-04')]=True
    e=scorer.score(date(2020,11,30))['events'][0]
    assert e['occurrence_score']==100 and e['outlier'] and e['first_recorded']
    assert e['reference_years']==[] and e['seasonal_occurrence_score'] is None
    assert e['activity_score'] is None and e['support']=='limited'


def test_incomplete_historical_day_does_not_erase_positive_prior_evidence():
    scorer=make_scorer([('2018-11-30',2,0.,1),('2020-11-30',1,0.,1)])
    scorer.activity['viirs_valid'][day('2018-11-30')]=False
    e=next(e for e in scorer.score(date(2020,11,30))['events'] if e['id']==1)
    assert not e['first_recorded']


def test_same_event_cannot_be_its_own_reference_across_years():
    scorer=make_scorer([('2019-12-31',1,0.,10),('2020-01-05',1,0.,10)])
    e=scorer.score(date(2020,1,5))['events'][0]
    assert e['active_reference_years']==[] and e['positive_reference_windows']==0


def test_outage_and_archive_boundary_are_unavailable():
    scorer=make_scorer([('2020-11-30',1,0.,2)])
    scorer.activity['viirs_valid'][day('2020-12-01')]=False
    assert scorer.score(date(2020,11,30))['status']=='incomplete_observations'
    assert scorer.score(EPOCH)['status']=='incomplete_observations'


def test_custom_bbox_selects_events_by_actual_reports():
    scorer=make_scorer([('2020-11-30',1,0.,2)])
    r=scorer.score(date(2020,11,30),bounds=(-118,34,-117,35))
    assert r['events']==[] and r['events_total']==0 and r['status']=='ok'


def test_event_endpoint_contract(monkeypatch):
    scorer=make_scorer([('2020-11-30',1,0.,2)])
    monkeypatch.setattr(api,'event_scorer',lambda:scorer)
    api.selected_event_activity.cache_clear()
    with TestClient(api.app) as client:
        r=client.get('/api/event-outliers',params={'anchor_date':'2020-11-30','include_points':True})
        assert r.status_code==200 and len(r.json()['points'])==2
        assert r.json()['events'][0]['outlier']
        for params in [{'anchor_date':'2026-01-01'},{'anchor_date':'2020-11-30','window_days':32},
                       {'anchor_date':'2020-11-30','reference':'all'},
                       {'anchor_date':'2020-11-30','bbox':'nan,32,-114,42'}]:
            assert client.get('/api/event-outliers',params=params).status_code==422
    api.selected_event_activity.cache_clear()


def test_mismatched_prepared_track_pair_is_rejected(tmp_path,monkeypatch):
    (tmp_path/'observations.npz').write_bytes(b'observation-snapshot')
    (tmp_path/'activity_events.npz').write_bytes(b'different-track-artifact')
    (tmp_path/'activity_events.json').write_text(json.dumps({'source_sha256':hashlib.sha256(b'observation-snapshot').hexdigest(),'tracks_sha256':'wrong','events':{}}))
    monkeypatch.setattr(api,'DATA',tmp_path)
    api.event_scorer.cache_clear()
    with pytest.raises(api.HTTPException) as error:
        api.event_scorer()
    assert error.value.status_code==503
    api.event_scorer.cache_clear()

@pytest.mark.parametrize('anchor,window,start,end', [
    ('2021-02-14',28,'2021-02-01','2021-02-28'),
    ('2020-02-15',29,'2020-02-01','2020-02-29'),
    ('2020-09-15',30,'2020-09-01','2020-09-30'),
    ('2020-07-16',31,'2020-07-01','2020-07-31'),
    ('2020-09-01',2,'2020-09-01','2020-09-02'),
])
def test_event_map_window_handoff(monkeypatch, anchor, window, start, end):
    scorer = make_scorer([('2019-01-01',1,0.,1)])
    monkeypatch.setattr(api, 'event_scorer', lambda: scorer)
    api.selected_event_activity.cache_clear()
    with TestClient(api.app) as client:
        response = client.get('/api/event-outliers',params={'anchor_date':anchor,'window_days':window})
        assert response.status_code == 200
        result = response.json()
        assert (result['start_date'],result['end_date']) == (start,end)
    api.selected_event_activity.cache_clear()
