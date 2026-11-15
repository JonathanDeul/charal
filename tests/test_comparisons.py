"""Comparison regressions: missing years, equal-age histories and future exclusion."""
from datetime import date, timedelta
from types import SimpleNamespace
import numpy as np
import pytest
from backend.comparisons import compare_years, FireComparison
from backend.fire_events import EPOCH, project


def test_annual_gaps_not_ranked_and_raw_partial_viirs_excluded():
    rows = [dict(year=y,month=m,viirs_count=10,harmonized_count=20,source='observed_viirs')
            for y in (2012,2013,2014,2015) for m in range(1,13)]
    rows[25].update(viirs_missing_day_count=1,harmonized_count=None)
    rows[38]['viirs_count']=0
    r=compare_years(rows,2012,2015,'viirs')['years']
    assert r[0]['total'] is None  # VIIRS startup year
    assert r[1]['total']==120 and r[1]['rank']==1
    assert r[2]['total'] is None and r[2]['available_months']==11
    assert r[3]['total']==110 and r[3]['rank']==2
    assert compare_years(rows,2013,2014,'harmonized')['years'][1]['total'] is None


def make_comparison():
    days=[];tracks=[]
    # Earlier track, target, future track, and an earlier December track whose
    # equal-age comparison crosses into the target year and must be excluded.
    for track,start,offsets in [(1,'2019-08-01',[0,1,8]),(2,'2020-08-01',[0,1,1,8]),
                                (3,'2021-08-01',[0]),(4,'2019-12-31',[0])]:
        for offset in offsets:
            days.append((date.fromisoformat(start)-EPOCH).days+offset);tracks.append(track)
    obs=dict(day=np.array(days),sensor=np.ones(len(days)),latitude=np.full(len(days),38.),longitude=np.full(len(days),-120.))
    tracks=np.array(tracks)
    scorer=SimpleNamespace(obs=obs,track_slices={i:None for i in (1,2,3,4)},
                           members=lambda i:np.flatnonzero(tracks==i),metadata={},
                           xy=project(obs['latitude'],obs['longitude']),
                           activity={'viirs_valid':np.ones((date(2026,1,1)-EPOCH).days,dtype=bool)})
    return FireComparison(scorer)


def test_equal_age_only_prior_years_and_no_future_detections():
    data=make_comparison()
    r=data.compare(2,date(2020,8,2))
    assert r['age_days']==2 and r['target']['total']==3
    assert r['target']['cumulative']==[1,3]
    assert r['reference_events']==1
    assert r['analogues'][0]['total']==2
    assert r['percentile']==100
    assert all(e['id']!=3 for e in r['analogues'])
    assert data.compare(1,date(2019,8,2))['percentile'] is None


def test_gaps_invalidate_target_and_reference():
    data=make_comparison()
    day=(date(2019,8,2)-EPOCH).days
    data.scorer.activity['viirs_valid'][day]=False
    assert data.compare(2,date(2020,8,2))['reference_events']==0
    data.scorer.activity['viirs_valid'][(date(2020,8,2)-EPOCH).days]=False
    assert data.compare(2,date(2020,8,2))['status']=='incomplete_observations'


def test_historical_event_selection_uses_only_past_week_and_region():
    data=make_comparison()
    listed=data.list_events(date(2020,8,2),(-121,37,-119,39))
    assert [e['id'] for e in listed]==[2]
    assert listed[0]['latitude']==38. and listed[0]['longitude']==-120.
    # A later detection far away must not move the cutoff's map marker.
    future=(data.obs['day'] > (date(2020,8,2)-EPOCH).days)
    data.obs['latitude'][future]=34.
    assert data.list_events(date(2020,8,2),(-121,37,-119,39))[0]['latitude']==38.
    assert data.list_events(date(2020,8,2),(-118,33,-117,34))==[]
    with pytest.raises(ValueError):data.compare(2,date(2020,7,31))
