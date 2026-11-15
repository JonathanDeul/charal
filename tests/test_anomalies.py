"""Scientific invariants for circular seasons, same-duration support and ranks."""
from datetime import date
import json

import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend.anomalies import (EPOCH, END, calendar_axis, seasonal_weights,
                               rolling, reference_weights, weighted_stats,
                               fit_seasonal_ratios, score_activity)
import backend.app as api


def day(text):
    return (date.fromisoformat(text) - EPOCH).days


@pytest.fixture
def daily():
    n = (END - EPOCH).days + 1
    years, season = calendar_axis(n)
    m = np.ones((n, 2), dtype=np.int32)
    v = m * 2
    valid = np.arange(n) >= day('2012-01-20')
    return {'modis': m, 'viirs': v, 'modis_valid': np.ones(n, dtype=bool),
            'viirs_valid': valid, 'years': years, 'season': season,
            'ratios': np.full(366, 2.), 'latitude': np.array([38.25, 34.25]),
            'longitude': np.array([-120.25, -118.25])}


def test_soft_season_crosses_month_and_year_boundaries(daily):
    s = daily['season']
    november = seasonal_weights(s, s[day('2020-11-30')], 30)
    assert november[day('2019-12-01')] > .99
    assert november[day('2019-12-15')] > 0
    assert november[day('2019-12-31')] == 0
    december = seasonal_weights(s, s[day('2020-12-31')], 30)
    assert december[day('2019-01-01')] > .99
    assert s[day('2019-03-01')] == s[day('2020-03-01')]
    leap = seasonal_weights(s, s[day('2020-02-29')], 30)
    assert leap[day('2019-02-28')] > .99 and leap[day('2019-03-01')] > .99


def test_actual_daily_counts_not_spread_from_month_totals():
    values = np.zeros((40, 1)); values[29] = 70
    sums, valid = rolling(values, np.ones(40, dtype=bool), 7)
    assert sums[29, 0] == 70
    assert sums[20, 0] == 0
    assert not valid[0] and not valid[-1]


def test_even_window_and_gap_support():
    values = np.ones((40, 1)); valid = np.ones(40, dtype=bool); valid[20] = False
    sums, complete = rolling(values, valid, 14)
    assert sums[13, 0] == 14
    assert not complete[13]  # Seven days after center includes gap at day 20.
    assert complete[12]


def test_target_year_and_crossing_windows_excluded(daily):
    n = len(daily['years'])
    weights, years = reference_weights(daily['years'], daily['season'], np.ones(n, dtype=bool), day('2020-12-31'), 7, 30)
    assert 2020 not in years
    assert 2021 not in years  # Target measurement itself extends into 2021.
    assert weights[day('2019-12-31')] == 0  # Measurement overlaps target year.
    assert weights[day('2021-01-01')] == 0
    assert weights[day('2021-01-04')] == 0
    assert weights[day('2018-12-31')] > 0
    for year in years:
        assert weights[daily['years'] == year].sum() == pytest.approx(1)


def test_reference_requires_ten_years(daily):
    valid = daily['years'] >= 2018
    weights, years = reference_weights(daily['years'], daily['season'], valid, day('2020-11-30'), 7, 30)
    assert len(years) < 10 and not weights.any()


def test_rank_ties_and_zero_activity():
    result = weighted_stats(np.array([[0, 1], [0, 2], [0, 3]]), np.array([0, 2]), np.ones(3))
    assert result[0].tolist() == [0, 50]
    assert result[1].tolist() == [0, 2]


def test_scores_compare_equal_windows_and_area_summed_before_ranking(daily):
    anchor = day('2020-11-30')
    daily['viirs'][anchor, 0] = 200
    r = score_activity(daily, date(2020,11,30))
    assert r['status'] == 'ok'
    assert r['start_date'] == '2020-11-27' and r['end_date'] == '2020-12-03'
    assert r['cells'][0]['activity'] == 212
    assert r['cells'][0]['score'] == 100
    assert r['cells'][1]['score'] == 50
    assert r['summary']['activity'] == 226
    assert r['summary']['score'] == 100  # Not sum or mean of cell percentiles.
    assert len(r['reference_years']) == 24
    json.dumps(r, allow_nan=False)


def test_historical_modis_and_viirs_only_reference_sensitivity(daily):
    anchor = day('2020-11-30')
    daily['modis'][daily['years'] < 2012] = 20
    daily['viirs'][anchor, 0] = 20
    r = score_activity(daily, date(2020,11,30))
    assert r['cells'][0]['viirs_reference_score'] == 100
    assert r['cells'][0]['score'] < 95
    assert r['cells'][0]['reference_sensitive']


def test_modis_backcast_uses_daily_calibration(daily):
    r = score_activity(daily, date(2011,11,30))
    assert r['source'] == 'modeled_modis' and r['cells'][0]['activity'] == 14
    assert r['cells'][0]['score'] == 50
    r = score_activity(daily, date(2011,11,30), reference='viirs')
    assert r['status'] == 'incomplete_observations'


def test_complete_gap_window_is_unavailable_not_zero(daily):
    daily['viirs_valid'][day('2020-12-01')] = False
    assert score_activity(daily, date(2020,11,30))['status'] == 'incomplete_observations'
    assert score_activity(daily, EPOCH)['status'] == 'incomplete_observations'


def test_no_supported_cell_is_unavailable(daily):
    r = score_activity(daily, date(2020,11,30), bounds=(-120.2,38,-120.1,38.3))
    assert r['status'] == 'no_grid_coverage' and r['summary'] is None


def test_calibration_ignores_later_years_and_supports_year_exclusion(daily):
    args = [daily[k] for k in ['modis','viirs']]
    paired = daily['modis_valid'] & daily['viirs_valid']
    ratios = fit_seasonal_ratios(*args, paired, daily['years'], daily['season'])
    assert np.allclose(ratios, 2)
    daily['viirs'][daily['years'] >= 2021] = 5000
    assert np.allclose(fit_seasonal_ratios(*args, paired, daily['years'], daily['season']), ratios)
    daily['viirs'][daily['years'] == 2013] = 100
    assert np.allclose(fit_seasonal_ratios(*args, paired, daily['years'], daily['season'], exclude_year=2013), ratios)
    daily['viirs'][daily['years'] == 2014] = 100
    assert np.allclose(fit_seasonal_ratios(*args, paired, daily['years'], daily['season'], exclude_year=[2013,2014]), ratios)


def test_full_state_keeps_boundary_cells_with_centers_outside_bbox(daily):
    daily['latitude'][0] = 32.25
    r = score_activity(daily, date(2020,11,30))
    assert len(r['cells']) == 2 and r['summary']['activity'] == 28
    custom = score_activity(daily, date(2020,11,30), bounds=(-121,32.5,-120,33))
    assert custom['status'] == 'no_grid_coverage'


def test_api_contract_and_parameter_validation(daily, monkeypatch):
    monkeypatch.setattr(api, 'activity_dataset', lambda: daily)
    api.selected_activity.cache_clear()
    with TestClient(api.app) as client:
        r = client.get('/api/activity-outliers', params={'anchor_date':'2020-11-30'})
        assert r.status_code == 200 and r.json()['status'] == 'ok'
        for params in [{'anchor_date':'2026-01-01'}, {'anchor_date':'2020-02-30'},
                       {'anchor_date':'2020-11-30','window_days':32},
                       {'anchor_date':'2020-11-30','reference':'all'},
                       {'anchor_date':'2020-11-30','season_days':0},
                       {'anchor_date':'2020-11-30','threshold':101},
                       {'anchor_date':'2020-11-30','bbox':'nan,32,-114,42'}]:
            assert client.get('/api/activity-outliers', params=params).status_code == 422
    api.selected_activity.cache_clear()

@pytest.mark.parametrize('anchor,window,start,end', [
    ('2021-02-14',28,'2021-02-01','2021-02-28'),
    ('2020-02-15',29,'2020-02-01','2020-02-29'),
    ('2020-09-15',30,'2020-09-01','2020-09-30'),
    ('2020-07-16',31,'2020-07-01','2020-07-31'),
    ('2020-09-01',2,'2020-09-01','2020-09-02'),
])
def test_map_window_handoff_preserves_exact_dates(daily, monkeypatch, anchor, window, start, end):
    monkeypatch.setattr(api, 'activity_dataset', lambda: daily)
    api.selected_activity.cache_clear()
    with TestClient(api.app) as client:
        response = client.get('/api/activity-outliers', params={'anchor_date':anchor, 'window_days':window})
        assert response.status_code == 200
        result = response.json()
        assert (result['start_date'],result['end_date']) == (start,end)
        assert result['summary']['activity'] == window*4
    api.selected_activity.cache_clear()
