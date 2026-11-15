"""API contracts that protect period, selection and missing-data semantics."""
import csv
from datetime import date
import io

import numpy as np
import pytest
from fastapi.testclient import TestClient

import backend.app as api


@pytest.fixture
def client(monkeypatch):
    epoch = date(2001, 1, 1)
    rows = [dict(date='2011-12-01', year=2011, month=12, latitude=38.25, longitude=-120.25,
                 modis_count=2, viirs_count=None, harmonized_count=5.0, modeled_count=5.0,
                 source='modeled_modis', lower=1, upper=9),
            dict(date='2024-07-01', year=2024, month=7, latitude=38.25, longitude=-120.25,
                 modis_count=1, viirs_count=1, harmonized_count=None, modeled_count=2.5,
                 source='incomplete_reference', lower=None, upper=None,
                 viirs_missing_day_count=10, known_gap=True)]
    state = {'observations': {'latitude': np.array([38.1,38.2,38.1,34.0]),
                              'longitude': np.array([-120.1,-120.1,-120.1,-118.0]),
                              'day': np.array([(date(y,m,d)-epoch).days for y,m,d in [(2011,12,31),(2024,7,1),(2024,8,1),(2024,7,1)]]),
                              'sensor': np.array([0,1,1,0]), 'frp': np.array([1.,2.,3.,4.])},
             'events': [{'id':'1','name':'=untrusted','year':2024,'area_ha':200,'latitude':38.2,'longitude':-120.2}],
             'analysis': {'schema_version':1,'generated_at':'2026-11-14','period':{'start':'2001-01-01','end':'2025-12-31'},
                          'harmonization':{'monthly': rows,'cell_monthly':rows},
                          'extremes':{'status':'insufficient_data','n_events':1,'p_value':None}},
             'boundary': {'type':'FeatureCollection','features':[]}}
    monkeypatch.setattr(api, 'dataset', lambda:state)
    api.selected_months.cache_clear()
    api.selected_extremes.cache_clear()
    yield TestClient(api.app)
    api.selected_months.cache_clear()
    api.selected_extremes.cache_clear()


def test_missing_reference_is_not_zero(client):
    data = client.get('/api/overview', params={'bbox':'-121,37,-120,39','start_year':2024,'end_year':2024}).json()
    row = data['monthly'][0]
    assert row['harmonized_count'] is None
    assert row['viirs_count'] == 1
    assert row['source'] == 'incomplete_reference'
    assert row['viirs_missing_day_count'] == 10


def test_month_window_does_not_include_next_month(client):
    response = client.get('/api/hotspots', params={'year':2024,'month':7,'sensor':'VIIRS'})
    assert response.status_code == 200
    data=response.json()
    assert data['total'] == data['shown'] == 1
    assert data['points'][0][4] == '2024-07-01'


def test_pre_reference_period_remains_missing(client):
    row=client.get('/api/overview', params={'start_year':2011,'end_year':2011}).json()['monthly'][0]
    assert row['viirs_count'] is None
    assert row['harmonized_count'] == 5


@pytest.mark.parametrize('params',[{'bbox':'nan,32,-114,42'}, {'bbox':'-114,32,-124,42'},
                                  {'bbox':'-130,32,-114,42'}, {'start_year':2025,'end_year':2001},
                                  {'start_year':1999}])
def test_invalid_region_and_period_rejected(client,params):
    assert client.get('/api/overview',params=params).status_code == 422


def test_export_preserves_null_and_escapes_formulas(client):
    response=client.get('/api/export/monthly',params={'start_year':2011,'end_year':2011})
    row=list(csv.DictReader(io.StringIO(response.text)))[0]
    assert row['viirs_count'] == ''
    assert row['source']=='modeled_modis'
    fires=client.get('/api/export/fires').text
    assert "'=untrusted" in fires
    assert 'attachment' in response.headers['content-disposition']


def test_no_known_gap_bootstrap_is_fabricated(client):
    response=client.get('/api/extremes',params={'start_year':2024,'end_year':2024})
    assert response.status_code==200
    data=response.json()
    assert data['p_value'] is None
    assert data['status']=='insufficient_data'


def test_bbox_raw_point_selection_differs_from_grid_approximation(client):
    response=client.get('/api/overview',params={'bbox':'-120.15,38,-120.05,38.3','start_year':2024,'end_year':2024})
    data=response.json()
    assert data['summary']['viirs_count']==2
    assert data['monthly'][0]['viirs_count'] is None
    assert data['monthly'][0]['harmonized_count'] is None
    assert data['monthly'][0]['source']=='no_grid_coverage'
    assert data['spatial_approximation']


def test_fire_map_uses_all_observations_and_deduplicates_detection_days(client, monkeypatch):
    state = api.dataset()
    epoch = date(2001, 1, 1)
    # Three overlapping center assignments, two sensors, only two distinct dates.
    obs = {'latitude': np.array([38.1]*4), 'longitude': np.array([-120.1]*4),
           'day': np.array([(date(2024,7,d)-epoch).days for d in [1,1,3,31]]),
           'sensor': np.array([0,1,1,1]), 'frp': np.array([10.,20.,30.,float('nan')]),
           'scan': np.array([1.,.4,.4,.4]), 'track': np.array([1.,.4,.4,.4]),
           'time': np.array([930,1330,1345,1400]), 'satellite': np.array([0,2,2,2])}
    monkeypatch.setitem(state, 'observations', obs)
    result = client.get('/api/fire-map', params={'year':2024,'month':7,'sensor':'all'}).json()
    assert result['total'] == len(result['footprints']) == 4
    assert result['sampled'] is False
    assert len(result['cells']) == 1
    cell = result['cells'][0]
    assert cell['days'] == 3  # Not 4 detections and not the 31-day date span.
    assert cell['max_frp'] == 30
    assert cell['sources'] == 3
    assert cell['first'] == '2024-07-01' and cell['last'] == '2024-07-31'
    assert result['footprints'][0][7] == '0930'
    assert result['footprints'][3][3] is None
    day_result = client.get('/api/fire-map', params={'year':2024,'month':7,'sensor':'all','day':1}).json()
    assert day_result['total'] == 2 and day_result['cells'][0]['days'] == 1
    viirs = client.get('/api/fire-map', params={'year':2024,'month':7,'sensor':'VIIRS'}).json()
    assert viirs['total'] == 3 and viirs['cells'][0]['sources'] == 2
    assert client.get('/api/fire-map', params={'year':2024,'month':2,'day':30}).status_code == 422
    empty = client.get('/api/fire-map', params={'year':2024,'month':8}).json()
    assert empty['total'] == 0 and empty['cells'] == []


def test_fire_map_requires_geometry_snapshot(client):
    assert client.get('/api/fire-map').status_code == 503


def test_fire_map_animation_window_crosses_year_boundary(client, monkeypatch):
    obs = {'latitude': np.array([38.1]*5), 'longitude': np.array([-120.1]*5),
           'day': np.array([(date.fromisoformat(d)-api.EPOCH).days for d in
                            ['2023-12-30', '2023-12-31', '2024-01-01', '2024-01-02', '2024-01-01']]),
           'sensor': np.array([1,1,1,1,0]), 'frp': np.array([100.,20.,30.,200.,40.]),
           'scan': np.array([.4]*5), 'track': np.array([.4]*5),
           'time': np.array([930]*5), 'satellite': np.array([2,2,2,2,0])}
    monkeypatch.setitem(api.dataset(), 'observations', obs)
    params = {'start_date':'2023-12-31', 'end_date':'2024-01-01', 'sensor':'VIIRS'}
    response = client.get('/api/fire-map', params=params)
    assert response.status_code == 200
    result = response.json()
    assert result['total'] == 2
    assert [r[4] for r in result['footprints']] == ['2023-12-31', '2024-01-01']
    assert result['start_date'] == '2023-12-31' and result['end_date'] == '2024-01-01'
    assert result['cells'][0]['days'] == 2 and result['cells'][0]['max_frp'] == 30
    empty = client.get('/api/fire-map', params={**params, 'bbox':'-119,33,-118,34'}).json()
    assert empty['total'] == 0 and empty['cells'] == []
    empty_day = client.get('/api/fire-map', params={**params, 'start_date':'2024-01-03', 'end_date':'2024-01-03'}).json()
    assert empty_day['total'] == 0


@pytest.mark.parametrize('params', [
    {'start_date':'2024-01-01'}, {'end_date':'2024-01-01'},
    {'start_date':'2024-02-30', 'end_date':'2024-03-01'},
    {'start_date':'2024-02-01', 'end_date':'2024-01-01'},
    {'start_date':'2000-12-31', 'end_date':'2001-01-01'},
    {'start_date':'2025-12-31', 'end_date':'2026-01-01'},
    {'start_date':'2024-01-01', 'end_date':'2024-12-31'},
    {'start_date':'2024-01-01', 'end_date':'2024-01-02', 'day':1},
])
def test_fire_map_rejects_invalid_animation_windows(client, monkeypatch, params):
    obs = api.dataset()['observations']
    for key in ('scan', 'track', 'time', 'satellite'):
        monkeypatch.setitem(obs, key, np.ones(4))
    assert client.get('/api/fire-map', params=params).status_code == 422


def test_year_comparison_route_keeps_partial_year_unranked(client):
    response=client.get('/api/compare-years',params={'start_year':2024,'end_year':2024})
    assert response.status_code==200
    assert response.json()['years'][0]['total'] is None
    assert client.get('/api/compare-years',params={'reference':'all'}).status_code==422
    assert client.get('/api/compare-years',params={'end_year':2026}).status_code==422


@pytest.mark.parametrize('as_of',['2012-12-31','2026-01-01','invalid'])
def test_fire_comparison_rejects_dates_outside_frozen_reference(client,as_of):
    assert client.get('/api/compare-fire',params={'as_of':as_of}).status_code==422
