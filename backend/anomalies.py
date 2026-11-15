"""Exploratory seasonal activity ranks on a fixed reporting scale.

Measurement windows use real daily detections. Reference windows have the same
length, a circular calendar kernel, equal total weight per reference year, and
never overlap any calendar year touched by the target. Ranks are descriptive,
not p-values.
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np

EPOCH = date(2001, 1, 1)
END = date(2025, 12, 31)
WINDOWS = (1, 3, 7, 14)


def calendar_axis(days: int) -> tuple[np.ndarray, np.ndarray]:
    dates = [EPOCH + timedelta(days=i) for i in range(days)]
    # A leap-year template preserves month/day alignment after February in all
    # years. Feb 29 has its own position; December and January are adjacent.
    season = np.array([(date(2000, d.month, d.day) - date(2000, 1, 1)).days for d in dates])
    return np.array([d.year for d in dates]), season


def seasonal_weights(season: np.ndarray, center: int, radius: int) -> np.ndarray:
    distance = np.abs(season - center)
    distance = np.minimum(distance, 366 - distance)
    return np.where(distance < radius, .5 * (1 + np.cos(np.pi * distance / radius)), 0.)


def fit_seasonal_ratios(modis, viirs, paired, years, season, radius=30, exclude_year=None):
    """Smooth ratio of training totals, never a mean of unstable daily ratios."""
    train = paired & (years >= 2013) & (years <= 2020)
    if exclude_year is not None:
        train &= ~np.isin(years, np.atleast_1d(exclude_year))
    m = np.bincount(season[train], weights=modis[train].sum(axis=1), minlength=366)
    v = np.bincount(season[train], weights=viirs[train].sum(axis=1), minlength=366)
    if m.sum() <= 0:
        raise ValueError('No eligible MODIS calibration reports')
    fallback = v.sum() / m.sum()
    ratios = []
    for center in range(366):
        weights = seasonal_weights(np.arange(366), center, radius)
        denominator = weights @ m
        ratios.append(float(weights @ v / denominator) if denominator > 0 else float(fallback))
    return np.array(ratios)


def rolling(values: np.ndarray, valid: np.ndarray, window: int):
    """Centered, complete windows; even lengths have the extra day after center."""
    n = len(values)
    left, right = (window - 1) // 2, window // 2
    centers = np.arange(n)
    starts, stops = centers - left, centers + right + 1
    inside = (starts >= 0) & (stops <= n)
    starts, stops = np.clip(starts, 0, n), np.clip(stops, 0, n)
    sums = np.concatenate([np.zeros((1, values.shape[1])), np.cumsum(values, axis=0)], axis=0)
    bad = np.r_[0, np.cumsum(~valid)]
    return sums[stops] - sums[starts], inside & ((bad[stops] - bad[starts]) == 0)


def reference_weights(years, season, valid, anchor, window, radius, minimum_years=10):
    target_years = np.unique(years[max(0, anchor-(window-1)//2):anchor+window//2+1])
    # Exclude any candidate whose measurement support touches a target year,
    # including spillover of the target itself and of reference windows.
    outside = ~np.isin(years, target_years)
    _, avoids_target = rolling(np.zeros((len(years), 1)), outside, window)
    weights = seasonal_weights(season, season[anchor], radius) * valid * avoids_target
    included = []
    for year in np.unique(years):
        mask = years == year
        total = weights[mask].sum()
        if total > 0:
            weights[mask] /= total
            included.append(int(year))
    if len(included) < minimum_years:
        weights[:] = 0
    return weights, included


def weighted_stats(values, target, weights):
    keep = weights > 0
    if not np.any(keep):
        return None
    v, w = values[keep], weights[keep]
    total = w.sum()
    # Midranks handle tied positive counts. Zero observed activity is explicitly
    # assigned zero upper-activity anomaly, rather than flagging a sea of zeros.
    scores = 100 * (w[:, None] * ((v < target) + .5 * (v == target))).sum(axis=0) / total
    scores = np.where(target > 0, scores, 0.)
    order = np.argsort(v, axis=0, kind='stable')
    sorted_values = np.take_along_axis(v, order, axis=0)
    cumulative = np.cumsum(w[order], axis=0)
    median = sorted_values[np.argmax(cumulative >= total / 2, axis=0), np.arange(v.shape[1])]
    return scores, median


def activity_series(data, reference='harmonized', target_years=None):
    ratios = data['ratios']
    if target_years is not None and 'ratios_by_year' in data:
        first_year = int(target_years[0])
        ratios = data['ratios_by_pair'][first_year - 2001] if len(target_years) > 1 else data['ratios_by_year'][first_year - 2001]
    estimated = data['modis'].astype(float) * ratios[data['season'], None]
    if reference == 'viirs':
        return data['viirs'].astype(float), data['viirs_valid'], np.zeros(len(estimated), dtype=bool)
    use_viirs = np.arange(len(estimated)) >= (date(2012, 2, 1) - EPOCH).days
    values = np.where(use_viirs[:, None], data['viirs'], estimated)
    valid = np.where(use_viirs, data['viirs_valid'], data['modis_valid'])
    return values, valid, ~use_viirs


def score_activity(data, anchor_date: date, window=7, radius=30,
                   bounds=(-124.5, 32.5, -114.1, 42.1), reference='harmonized', threshold=95.):
    anchor = (anchor_date - EPOCH).days
    lat, lon = data['latitude'], data['longitude']
    west, south, east, north = bounds
    selected = np.ones(len(lat), dtype=bool) if tuple(bounds) == (-124.5, 32.5, -114.1, 42.1) else (lon >= west) & (lon <= east) & (lat >= south) & (lat <= north)
    result = {'status': 'ok', 'anchor_date': anchor_date.isoformat(), 'window_days': window,
              'season_days': radius, 'reference': reference, 'threshold': threshold,
              'grid_degrees': .5, 'reference_period': '2001–2025' if reference == 'harmonized' else '2012–2025',
              'start_date': (anchor_date - timedelta(days=(window-1)//2)).isoformat(),
              'end_date': (anchor_date + timedelta(days=window//2)).isoformat(),
              'cells': [], 'summary': None, 'reference_years': [], 'reference_windows': 0,
              'interpretation': 'Weighted historical percentile of reported activity; not a probability, fire count, burned area, or hazard score.',
              'experimental': True,
              'method': {'seasonal_kernel': 'Raised cosine on a 366-day leap-year month/day template; zero at seasonal radius.',
                         'year_weighting': 'Each eligible reference anchor year has equal total weight.',
                         'exclusion': 'Every reference window touching any calendar year covered by the target measurement is excluded.',
                         'rank': '100 × weighted fraction below target plus half the tied weight; zero target maps to zero.',
                         'minimum_reference_years': 10,
                         'spatial_support': 'Fixed California-intersecting 0.5° grid. Custom areas select cell centers; statewide includes all boundary cells.',
                         'uncertainty': 'Descriptive correlated-window rank, not a calibrated p-value or predictive interval. VIIRS-reference sensitivity does not quantify all calibration uncertainty.'}}
    if not selected.any():
        result['status'] = 'no_grid_coverage'
        return result
    left, right = anchor - (window-1)//2, anchor + window//2 + 1
    target_years = np.unique(data['years'][max(0, left):right])
    result['excluded_target_years'] = target_years.tolist()
    series, valid, modeled = activity_series(data, reference, target_years)
    rolled, complete = rolling(series[:, selected], valid, window)
    if not 0 <= anchor < len(series) or not complete[anchor]:
        result['status'] = 'incomplete_observations'
        return result
    weights, years = reference_weights(data['years'], data['season'], complete, anchor, window, radius)
    result.update(reference_years=years, reference_windows=int(np.count_nonzero(weights)))
    if not weights.any():
        result['status'] = 'insufficient_reference'
        return result
    result['modeled_reference_fraction'] = float(weights @ modeled / weights.sum())
    result['source'] = 'modeled_modis' if modeled[left:right].all() else 'observed_viirs' if not modeled[left:right].any() else 'mixed_transition'
    result['early_platform_caution'] = result['start_date'] < '2002-07-01'
    # Compare *the same target measurement* with a VIIRS-only reference, so this
    # sensitivity isolates the reference choice, not a different target sensor.
    viirs_rolled, viirs_complete = rolling(data['viirs'][:, selected].astype(float), data['viirs_valid'], window)
    viirs_weights, viirs_years = reference_weights(data['years'], data['season'], viirs_complete, anchor, window, radius)
    result['viirs_reference_years'] = viirs_years

    def describe(values, observed_values):
        scores, medians = weighted_stats(values, values[anchor], weights)
        comparison = weighted_stats(observed_values, values[anchor], viirs_weights)
        rows = []
        for i, (score, median, activity) in enumerate(zip(scores, medians, values[anchor])):
            alternative = float(comparison[0][i]) if comparison is not None else None
            rows.append({'score': round(float(score), 2), 'activity': round(float(activity), 2),
                         'typical_activity': round(float(median), 2),
                         'viirs_reference_score': round(alternative, 2) if alternative is not None else None,
                         'reference_sensitive': bool(alternative is not None and ((score >= threshold) != (alternative >= threshold))),
                         'outlier': bool(score >= threshold and activity > 0)})
        return rows

    result['summary'] = describe(rolled.sum(axis=1, keepdims=True), viirs_rolled.sum(axis=1, keepdims=True))[0]
    cells = describe(rolled, viirs_rolled)
    for index, row in zip(np.flatnonzero(selected), cells):
        y, x = float(lat[index]), float(lon[index])
        row.update(latitude=y, longitude=x, bounds=[x-.25, y-.25, x+.25, y+.25])
    result['cells'] = cells
    result['outlier_cells'] = sum(r['outlier'] for r in cells)
    return result
