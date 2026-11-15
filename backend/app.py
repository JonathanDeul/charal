"""Read-only API for the frozen California study. No secrets needed at runtime."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from functools import lru_cache
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
from typing import Annotated

import numpy as np
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import Response

from backend.science import fit_extremes
from backend.anomalies import score_activity, WINDOWS
from backend.fire_events import EventScorer

DATA = Path(__file__).resolve().parents[1] / 'data' / 'processed'
STATE_BBOX = (-124.5, 32.5, -114.1, 42.1)
EPOCH = date(2001, 1, 1)

app = FastAPI(title='Charal California Observatory', version='1.0.0',
              description='Frozen 2001–2025 real-data research PoC. Detections are not distinct fires.')


@lru_cache(maxsize=1)
def dataset():
    required = ['observations.npz', 'events.json.gz', 'analysis.json.gz', 'california.geojson']
    if not all((DATA / p).exists() for p in required):
        raise HTTPException(503, 'Prepared study data is not available; run ingestion, analysis and packing.')
    with gzip.open(DATA / 'analysis.json.gz', 'rt') as f:
        analysis = json.load(f)
    if not analysis.get('harmonization'):
        raise HTTPException(503, 'Harmonization has not been prepared.')
    with gzip.open(DATA / 'events.json.gz', 'rt') as f:
        events = json.load(f)
    with np.load(DATA / 'observations.npz', allow_pickle=False) as f:
        observations = {k: f[k] for k in f.files}
    context = DATA / 'map-context.geojson'
    return {'analysis': analysis, 'events': events, 'observations': observations,
            'boundary': json.loads((DATA / 'california.geojson').read_text()),
            'map_context': json.loads(context.read_text()) if context.exists() else None}


def parse_bbox(bbox: str | None) -> tuple[float, float, float, float]:
    if not bbox:
        return STATE_BBOX
    try:
        values = tuple(float(x) for x in bbox.split(','))
        if len(values) != 4 or not all(np.isfinite(values)):
            raise ValueError
        w, s, e, n = values
        if w >= e or s >= n or w < STATE_BBOX[0] or s < STATE_BBOX[1] or e > STATE_BBOX[2] or n > STATE_BBOX[3]:
            raise ValueError
        return values
    except (TypeError, ValueError):
        raise HTTPException(422, 'bbox must be west,south,east,north within -124.5,32.5,-114.1,42.1') from None


def validate_years(start: int, end: int):
    if not 2001 <= start <= end <= 2025:
        raise HTTPException(422, 'Select years from 2001 through 2025, with start_year <= end_year.')


def full_state(bounds):
    return tuple(bounds) == STATE_BBOX


def event_selection(start: int, end: int, bounds):
    w, s, e, n = bounds
    return [r for r in dataset()['events'] if start <= r['year'] <= end and
            (full_state(bounds) or (r.get('latitude') is not None and r.get('longitude') is not None
                                    and w <= r['longitude'] <= e and s <= r['latitude'] <= n))]


def observation_mask(start: int, end: int, bounds, sensor: str = 'all'):
    observations = dataset()['observations']
    first = (date(start, 1, 1) - EPOCH).days
    last = (date(end + 1, 1, 1) - EPOCH).days
    mask = (observations['day'] >= first) & (observations['day'] < last)
    if not full_state(bounds):
        w, s, e, n = bounds
        mask &= ((observations['longitude'] >= w) & (observations['longitude'] <= e) &
                 (observations['latitude'] >= s) & (observations['latitude'] <= n))
    if sensor in ('MODIS', 'VIIRS'):
        mask &= observations['sensor'] == (sensor == 'VIIRS')
    return mask


@lru_cache(maxsize=64)
def selected_months(start: int, end: int, bounds: tuple):
    harmonization = dataset()['analysis']['harmonization']
    if full_state(bounds):
        return [{**r, 'date': r['date'][:7]} for r in harmonization['monthly'] if start <= r['year'] <= end]
    w, s, e, n = bounds
    result = {}
    for base in harmonization['monthly']:
        if not start <= base['year'] <= end:
            continue
        date_key = base['date'][:7]
        result[date_key] = {**base, 'date': date_key,
                           'modis_count': 0,
                           'viirs_count': None if base['viirs_count'] is None else 0,
                           'harmonized_count': None if base['harmonized_count'] is None else 0,
                           'modeled_count': 0, 'lower': None, 'upper': None}
        if 'baseline_modeled_count' in base:
            result[date_key]['baseline_modeled_count'] = 0
        for key in ('training_variability_lower90', 'training_variability_upper90'):
            if key in base:
                result[date_key][key] = None
        result[date_key]['interval_scope'] = 'No calibrated aggregate interval for this custom AOI'
    matched = False
    for row in harmonization['cell_monthly']:
        if not (start <= row['year'] <= end and w <= row['longitude'] <= e and s <= row['latitude'] <= n):
            continue
        matched = True
        target = result[row['date'][:7]]
        for key in ('modis_count', 'viirs_count', 'harmonized_count', 'modeled_count', 'baseline_modeled_count'):
            if row.get(key) is not None and (key != 'harmonized_count' or target['harmonized_count'] is not None):
                target[key] = (target[key] or 0) + row[key]
    if not matched:
        for target in result.values():
            for key in ('modis_count', 'viirs_count', 'harmonized_count', 'modeled_count', 'baseline_modeled_count'):
                target[key] = None
            target['source'] = 'no_grid_coverage'
    return list(result.values())


@app.get('/api/health')
def health():
    d = dataset()
    return {'status': 'ok', 'observations': len(d['observations']['day']),
            'period': d['analysis']['period'], 'schema_version': d['analysis']['schema_version']}


@app.get('/api/catalog')
def catalog():
    d = dataset()
    h = d['analysis']['harmonization']
    return {'title': 'Charal', 'period': d['analysis']['period'], 'bbox': STATE_BBOX,
            'boundary': d['boundary'], 'map_context': d.get('map_context'), 'harmonization': {k: v for k, v in h.items() if k not in ('cell_monthly', 'monthly')},
            'provenance': d['analysis'].get('provenance', {}),
            'generated_at': d['analysis']['generated_at'],
            'selection_note': 'Calendar: grid-cell centers. Detections: exact point coordinates. Perimeters: centroid selection, whole-event area.'}


@app.get('/api/overview')
def overview(start_year: int = 2001, end_year: int = 2025, bbox: str | None = None):
    validate_years(start_year, end_year)
    bounds = parse_bbox(bbox)
    rows = selected_months(start_year, end_year, bounds)
    obs = dataset()['observations']
    mask = observation_mask(start_year, end_year, bounds)
    events = event_selection(start_year, end_year, bounds)
    return {'monthly': rows, 'summary': {
        'modis_count': int(np.sum(mask & (obs['sensor'] == 0))),
        'viirs_count': int(np.sum(mask & (obs['sensor'] == 1))),
        'fire_count': len(events), 'perimeter_area_ha': sum(r['area_ha'] for r in events)},
        'selection': {'bbox': bounds, 'start_year': start_year, 'end_year': end_year},
        'spatial_approximation': not full_state(bounds)}


@lru_cache(maxsize=1)
def activity_dataset():
    path = DATA / 'activity_daily.npz'
    if not path.exists():
        raise HTTPException(503, 'Prepare seasonal activity with scripts/prepare_activity.py')
    with np.load(path, allow_pickle=False) as source:
        arrays = {key: source[key] for key in source.files}
    return arrays


@lru_cache(maxsize=32)
def selected_activity(anchor: date, window: int, radius: int, bounds: tuple, reference: str, threshold: float):
    return score_activity(activity_dataset(), anchor, window, radius, bounds, reference, threshold)


@app.get('/api/activity-outliers')
def activity_outliers(anchor_date: date,
                      window_days: Annotated[int, Query(ge=1, le=31)] = 7,
                      season_days: Annotated[int, Query(ge=15, le=60)] = 30,
                      reference: str = 'viirs', bbox: str | None = None,
                      threshold: Annotated[float, Query(ge=90, le=100)] = 95):
    if not date(2001, 1, 1) <= anchor_date <= date(2025, 12, 31):
        raise HTTPException(422, 'Anchor date must be within 2001–2025')
    if window_days not in (*WINDOWS, 2, 28, 29, 30, 31) or reference not in ('harmonized', 'viirs'):
        raise HTTPException(422, 'Choose a 1, 2, 3, 7, 14, 28, 29, 30 or 31 day window and harmonized or viirs reference')
    result = selected_activity(anchor_date, window_days, season_days, parse_bbox(bbox), reference, threshold)
    diagnostics = DATA / 'activity_diagnostics.json'
    metadata = DATA / 'activity_metadata.json'
    return {**result, 'diagnostics': json.loads(diagnostics.read_text()) if diagnostics.exists() else None,
            'calibration_metadata': json.loads(metadata.read_text()) if metadata.exists() else None}


@lru_cache(maxsize=1)
def event_scorer():
    if not (DATA/'activity_events.npz').exists() or not (DATA/'activity_events.json').exists():
        raise HTTPException(503, 'Prepare observed events with scripts/prepare_fire_events.py')
    metadata = json.loads((DATA/'activity_events.json').read_text())
    if metadata['source_sha256'] != hashlib.sha256((DATA/'observations.npz').read_bytes()).hexdigest():
        raise HTTPException(503, 'Event tracks are outdated; run scripts/prepare_fire_events.py')
    if metadata.get('tracks_sha256') != hashlib.sha256((DATA/'activity_events.npz').read_bytes()).hexdigest():
        raise HTTPException(503, 'Event tracks and metadata do not match; run scripts/prepare_fire_events.py')
    with np.load(DATA/'activity_events.npz',allow_pickle=False) as f:
        tracks = f['tracks']
    return EventScorer(dataset()['observations'], activity_dataset(), tracks, metadata['events'])


@lru_cache(maxsize=24)
def selected_event_activity(anchor, window, radius, bounds, reference, threshold, include_points):
    return event_scorer().score(anchor,window,radius,reference,threshold,bounds,include_points)


@app.get('/api/event-outliers')
def event_outliers(anchor_date: date,
                   window_days: Annotated[int, Query(ge=1,le=31)] = 7,
                   season_days: Annotated[int, Query(ge=15,le=60)] = 30,
                   reference: str = 'viirs', bbox: str | None = None,
                   threshold: Annotated[float, Query(ge=90,le=100)] = 95,
                   include_points: bool = False):
    if not date(2001,1,1) <= anchor_date <= date(2025,12,31):
        raise HTTPException(422, 'Anchor date must be within 2001–2025')
    if window_days not in (*WINDOWS, 2, 28, 29, 30, 31) or reference not in ('harmonized','viirs'):
        raise HTTPException(422, 'Choose a 1, 2, 3, 7, 14, 28, 29, 30 or 31 day window and harmonized or viirs reference')
    result = selected_event_activity(anchor_date,window_days,season_days,parse_bbox(bbox),reference,threshold,include_points)
    metadata = DATA/'activity_metadata.json'
    return {**result,'calibration_metadata':json.loads(metadata.read_text()) if metadata.exists() else None}


@app.get('/api/hotspots')
def hotspots(year: Annotated[int, Query(ge=2001, le=2025)] = 2020,
             month: Annotated[int, Query(ge=1, le=12)] = 9,
             sensor: str = 'all', bbox: str | None = None,
             limit: Annotated[int, Query(ge=1, le=15000)] = 10000):
    if sensor not in ('all', 'MODIS', 'VIIRS'):
        raise HTTPException(422, 'sensor must be all, MODIS or VIIRS')
    bounds = parse_bbox(bbox)
    obs = dataset()['observations']
    start = date(year, month, 1)
    end = date(year + (month == 12), month % 12 + 1, 1)
    mask = observation_mask(year, year, bounds, sensor)
    mask &= (obs['day'] >= (start-EPOCH).days) & (obs['day'] < (end-EPOCH).days)
    indices = np.flatnonzero(mask)
    total = len(indices)
    if total > limit:
        rng = np.random.default_rng(42)
        indices = np.sort(rng.choice(indices, limit, replace=False))
    points = [[round(float(obs['latitude'][i]), 5), round(float(obs['longitude'][i]), 5),
               'VIIRS' if obs['sensor'][i] else 'MODIS', round(float(obs['frp'][i]), 2),
               (EPOCH+timedelta(days=int(obs['day'][i]))).isoformat()] for i in indices]
    return {'points': points, 'total': total, 'shown': len(points), 'sampling': 'Seeded uniform sample if total exceeds limit',
            'units': 'reported thermal detections', 'period': f'{year}-{month:02d}'}


@app.get('/api/fire-map')
def fire_map(year: Annotated[int, Query(ge=2001, le=2025)] = 2020,
             month: Annotated[int, Query(ge=1, le=12)] = 9,
             sensor: str = 'VIIRS', bbox: str | None = None,
             day: Annotated[int | None, Query(ge=1, le=31)] = None,
             start_date: date | None = None, end_date: date | None = None):
    """Unsampled pixel proxies and center-assigned, equal-area 1 km activity cells."""
    if sensor not in ('all', 'MODIS', 'VIIRS'):
        raise HTTPException(422, 'sensor must be all, MODIS or VIIRS')
    bounds = parse_bbox(bbox)
    obs = dataset()['observations']
    if not {'scan', 'track', 'time', 'satellite'} <= obs.keys():
        raise HTTPException(503, 'Repack the NASA archive with scripts/pack_data.py for pixel geometry.')
    start = date(year, month, 1)
    end = date(year + (month == 12), month % 12 + 1, 1)
    if day is not None:
        try:
            start = date(year, month, day)
        except ValueError:
            raise HTTPException(422, 'Invalid calendar day') from None
        end = start + timedelta(days=1)
    if start_date is not None or end_date is not None:
        if start_date is None or end_date is None or day is not None:
            raise HTTPException(422, 'Provide both start_date and end_date, without day')
        if not date(2001, 1, 1) <= start_date <= end_date <= date(2025, 12, 31):
            raise HTTPException(422, 'Date range must be ordered and within 2001–2025')
        if (end_date - start_date).days >= 93:
            raise HTTPException(422, 'Select at most 93 days per map request')
        start, end = start_date, end_date + timedelta(days=1)
    mask = observation_mask(start.year, (end - timedelta(days=1)).year, bounds, sensor)
    mask &= (obs['day'] >= (start-EPOCH).days) & (obs['day'] < (end-EPOCH).days)
    indices = np.flatnonzero(mask)
    # Spherical Lambert cylindrical equal-area projection, standard parallel 37.5°N.
    # Fixed origin and support; this display grid is unrelated to count harmonization.
    radius = 6371008.8
    cos0 = np.cos(np.deg2rad(37.5))
    lon, lat = obs['longitude'][indices], obs['latitude'][indices]
    gx = np.floor(radius * cos0 * np.deg2rad(lon.astype(float)) / 1000).astype(int)
    gy = np.floor(radius * np.sin(np.deg2rad(lat.astype(float))) / cos0 / 1000).astype(int)
    groups = {}
    footprints = []
    invalid_geometry = 0
    for i, x, y in zip(indices.tolist(), gx.tolist(), gy.tolist()):
        d = (EPOCH + timedelta(days=int(obs['day'][i]))).isoformat()
        frp = float(obs['frp'][i])
        frp = round(frp, 2) if np.isfinite(frp) and frp >= 0 else None
        sensor_code = int(obs['sensor'][i])
        group = groups.setdefault((x, y), {'days': set(), 'first': d, 'last': d, 'frp': None, 'sources': 0, 'count': 0})
        group['days'].add(d)
        group['first'], group['last'] = min(group['first'], d), max(group['last'], d)
        if frp is not None:
            group['frp'] = max(group['frp'] or 0, frp)
        group['sources'] |= 2 if sensor_code else 1
        group['count'] += 1
        scan, track = float(obs['scan'][i]), float(obs['track'][i])
        if not (np.isfinite(scan) and np.isfinite(track) and scan > 0 and track > 0):
            invalid_geometry += 1
            continue
        footprints.append([round(float(obs['latitude'][i]), 5), round(float(obs['longitude'][i]), 5),
                           sensor_code, frp, d, round(scan, 3), round(track, 3),
                           f"{int(obs['time'][i]):04d}", int(obs['satellite'][i])])
    cells = []
    for (x, y), g in sorted(groups.items()):
        west, east = np.rad2deg(np.array([x, x+1]) * 1000 / (radius * cos0))
        south, north = np.rad2deg(np.arcsin(np.array([y, y+1]) * 1000 * cos0 / radius))
        cells.append({'bounds': [west, south, east, north], 'days': len(g['days']),
                      'first': g['first'], 'last': g['last'], 'max_frp': g['frp'],
                      'sources': g['sources'], 'count': g['count']})
    return {'footprints': footprints, 'cells': cells, 'total': len(indices),
            'invalid_geometry': invalid_geometry, 'sampled': False, 'grid_km': 1,
            'period': f'{year}-{month:02d}',
            'start_date': start.isoformat(), 'end_date': (end - timedelta(days=1)).isoformat(),
            'geometry': 'North-aligned scan/track rectangles; approximate pixel footprints, not burn scars.',
            'grid_method': '1 km equal-area cells, detections assigned by pixel center; distinct UTC dates, not continuous duration.'}


@lru_cache(maxsize=64)
def selected_extremes(start: int, end: int, bounds: tuple):
    if start == 2001 and end == 2025 and full_state(bounds):
        result = dict(dataset()['analysis']['extremes'])
    else:
        events = event_selection(start, end, bounds)
        result = fit_extremes([r['area_ha'] for r in events], bootstrap_replicates=0)
    p = result.get('p_value')
    if result.get('status') != 'fitted':
        result['interpretation'] = 'Too few eligible events for a defensible tail fit. Expand the area or time range.'
    elif p is None:
        result['interpretation'] = 'Exploratory fit for this selection. A goodness-of-fit bootstrap has not been run; the full-state, full-period analysis includes the precomputed statistical test.'
    elif p < .1:
        result['interpretation'] = 'The bootstrap test rejects a simple power-law tail for this sample. Large fires are common enough to create a heavy tail, but a power law does not fully explain its shape.'
    else:
        result['interpretation'] = 'This tail is statistically compatible with the fitted power law at the chosen threshold. This does not prove a power law or identify its physical mechanism.'
    result['selection_note'] = 'Perimeter centroids select complete event records; areas are not clipped to the selected region. Complex and component records may overlap.'
    return result


@app.get('/api/extremes')
def extremes(start_year: int = 2001, end_year: int = 2025, bbox: str | None = None):
    validate_years(start_year, end_year)
    return selected_extremes(start_year, end_year, parse_bbox(bbox))


@app.get('/api/export/{kind}')
def export(kind: str, start_year: int = 2001, end_year: int = 2025, bbox: str | None = None):
    validate_years(start_year, end_year)
    bounds = parse_bbox(bbox)
    suffix = f'charal-{kind}-{start_year}-{end_year}'
    if kind == 'analysis':
        result = {'selection': {'bbox': bounds, 'start_year': start_year, 'end_year': end_year},
                  'monthly': selected_months(start_year, end_year, bounds),
                  'extremes': selected_extremes(start_year, end_year, bounds),
                  'harmonization': {k: v for k, v in dataset()['analysis']['harmonization'].items() if k not in ('monthly', 'cell_monthly')},
                  'provenance': dataset()['analysis'].get('provenance', {}),
                  'input_sha256': dataset()['analysis'].get('input_sha256', {}),
                  'generated_at': dataset()['analysis']['generated_at']}
        return Response(json.dumps(result, allow_nan=False), media_type='application/json',
                        headers={'Content-Disposition': f'attachment; filename="{suffix}.json"'})
    if kind == 'monthly':
        records = selected_months(start_year, end_year, bounds)
        fields = ['date', 'year', 'month', 'modis_count', 'viirs_count', 'harmonized_count', 'modeled_count', 'baseline_modeled_count', 'source', 'lower', 'upper', 'sampling_regime', 'uncertainty_status', 'training_variability_lower90', 'training_variability_upper90', 'partial_reference', 'known_gap', 'reference_complete', 'modis_complete', 'modis_missing_day_count', 'viirs_missing_day_count']
    elif kind == 'fires':
        records = event_selection(start_year, end_year, bounds)
        fields = ['id', 'name', 'year', 'area_ha', 'latitude', 'longitude', 'complex_name', 'agency']
    else:
        raise HTTPException(404, 'Choose monthly, fires or analysis')
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fields, extrasaction='ignore')
    writer.writeheader()
    for r in records:
        # Prevent CSV formula evaluation for untrusted source names/identifiers.
        safe = {k: ("'"+v if isinstance(v, str) and v.startswith(('=', '+', '-', '@', '\t', '\r')) else v) for k,v in r.items()}
        writer.writerow(safe)
    return Response(stream.getvalue(), media_type='text/csv',
                    headers={'Content-Disposition': f'attachment; filename="{suffix}.csv"'})


@app.get('/api/compare-years')
def year_comparison(start_year: int = 2001, end_year: int = 2025, bbox: str | None = None,
                    reference: str = 'viirs'):
    from backend.comparisons import compare_years
    validate_years(start_year, end_year)
    if reference not in ('viirs', 'harmonized'):
        raise HTTPException(422, 'Choose viirs or harmonized')
    return compare_years(selected_months(start_year, end_year, parse_bbox(bbox)), start_year, end_year, reference)


@lru_cache(maxsize=1)
def fire_comparison_data():
    from backend.comparisons import FireComparison
    return FireComparison(event_scorer())


@app.get('/api/compare-fire')
def fire_comparison(as_of: date, event_id: int | None = None, bbox: str | None = None):
    if not date(2013,1,1) <= as_of <= date(2025,12,31):
        raise HTTPException(422, 'Choose a historical date in 2013–2025')
    bounds = parse_bbox(bbox)
    data = fire_comparison_data()
    if event_id is None:
        return {'events':data.list_events(as_of,bounds), 'as_of':as_of.isoformat()}
    if event_id not in data.entries:
        raise HTTPException(404, 'No supported VIIRS event with this ID')
    try:
        return data.compare(event_id,as_of)
    except ValueError as error:
        raise HTTPException(422,str(error)) from None
