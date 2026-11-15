#!/usr/bin/env python3
"""Audit the current outlier outcome without changing the detector.

Default: observed VIIRS, centered seven days, seasonal radius thirty days.
Every eligible daily cell window is examined. Perimeter links are retrospective
spatiotemporal associations, not independently verified fire identities.
"""
from pathlib import Path
from datetime import date, datetime, timedelta, timezone
from collections import Counter
import csv
import gzip
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
from scipy import stats, ndimage
from shapely.geometry import shape
from shapely import intersects_xy, prepare
from backend.anomalies import EPOCH, rolling, reference_weights, score_activity

OUT = ROOT / 'data/research/activity_outcomes'
WINDOW, RADIUS = 7, 30


def iso(day):
    return (EPOCH + timedelta(days=int(day))).isoformat()


def write_csv(path, rows):
    if not rows:
        return
    opener = gzip.open if path.suffix == '.gz' else open
    with opener(path, 'wt', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            writer.writerow({key:("'"+value if isinstance(value,str) and value.startswith(('=','+','-','@','\t','\r')) else value) for key,value in row.items()})


def ranked(values, target, weights):
    keep = weights > 0
    v, w = values[keep], weights[keep]
    score = 100 * (w[:, None] * ((v < target) + .5*(v == target))).sum(axis=0) / w.sum()
    zero = 100 * (w[:, None] * (v == 0)).sum(axis=0) / w.sum()
    return np.where(target > 0, score, 0), zero


def annual_ranks(values, complete, years):
    """Same-cell, year-balanced comparator with no seasonal conditioning."""
    output = np.full(values.shape, np.nan, dtype=np.float32)
    for year in range(2012,2026):
        target = np.flatnonzero(complete & (years == year))
        # Skip year-boundary target windows in this comparator; the production
        # seasonal audit below still includes them with its full exclusion.
        target = target[(years[target-3] == year) & (years[target+3] == year)]
        _, avoids_target = rolling(np.zeros((len(values),1)), years != year, WINDOW)
        keep = complete & avoids_target
        idx = np.flatnonzero(keep)
        weights = np.zeros(len(values))
        for refyear in np.unique(years[idx]):
            mask = keep & (years == refyear)
            weights[mask] = 1 / mask.sum()
        for cell in range(values.shape[1]):
            order = idx[np.argsort(values[idx, cell], kind='stable')]
            sorted_values = values[order, cell]
            cumulative = np.r_[0, np.cumsum(weights[order])]
            t = values[target, cell]
            lower = np.searchsorted(sorted_values, t, side='left')
            upper = np.searchsorted(sorted_values, t, side='right')
            output[target, cell] = np.where(t > 0, 50*(cumulative[lower]+cumulative[upper])/cumulative[-1], 0)
    return output


def window_audit(d):
    values, complete = rolling(d['viirs'].astype(float), d['viirs_valid'], WINDOW)
    fingerprint = hashlib.sha256((ROOT/'data/processed/activity_daily.npz').read_bytes()).hexdigest()
    cache = OUT/'scores.npz'
    signature = f'{fingerprint}:window{WINDOW}:radius{RADIUS}:v2'
    if cache.exists():
        with np.load(cache, allow_pickle=False) as f:
            if str(f['signature']) == signature:
                return values, complete, f['scores'], f['zero'], f['annual']
    scores = np.full(values.shape, np.nan, dtype=np.float32)
    zeros = np.full(values.shape, np.nan, dtype=np.float32)
    anchors = np.flatnonzero(complete)
    for j, anchor in enumerate(anchors):
        weights, _ = reference_weights(d['years'], d['season'], complete, anchor, WINDOW, RADIUS)
        if weights.any():
            scores[anchor], zeros[anchor] = ranked(values, values[anchor], weights)
        if j % 500 == 0:
            print(f'Window audit {j}/{len(anchors)}', flush=True)
    # Check optimized rank-only path against the actual application, including
    # a year-boundary window; no approximation is used in the audit rank.
    for text in ['2013-08-15','2017-12-10','2018-11-11','2020-12-31','2025-01-10']:
        anchor = (date.fromisoformat(text)-EPOCH).days
        actual = score_activity(d, date.fromisoformat(text), reference='viirs')
        if actual['status'] == 'ok':
            assert np.allclose(scores[anchor], [r['score'] for r in actual['cells']], atol=.0051)
    annual = annual_ranks(values, complete, d['years'])
    np.savez_compressed(cache, signature=np.array(signature), scores=scores, zero=zeros, annual=annual)
    return values, complete, scores, zeros, annual


def episodes(d, values, scores, zeros, annual):
    gy = np.floor(d['latitude']*2).astype(int)
    gx = np.floor(d['longitude']*2).astype(int)
    cube = np.zeros((len(values), gy.max()-gy.min()+1, gx.max()-gx.min()+1), dtype=bool)
    cube[:, gy-gy.min(), gx-gx.min()] = scores >= 95
    labels, n = ndimage.label(cube, structure=np.ones((3,3,3), dtype=int))
    ids = labels[:, gy-gy.min(), gx-gx.min()]
    rows = []
    for episode in range(1, n+1):
        days, cells = np.where(ids == episode)
        best = np.argmax(values[days, cells])
        day, cell = days[best], cells[best]
        rows.append({'episode':episode, 'first_anchor':iso(days.min()), 'last_anchor':iso(days.max()),
                     'flagged_cell_windows':len(days), 'cells':len(np.unique(cells)),
                     'anchor_days':len(np.unique(days)), 'peak_activity_anchor':iso(day),
                     'latitude':float(d['latitude'][cell]), 'longitude':float(d['longitude'][cell]),
                     'peak_window_activity':float(values[day,cell]), 'score_at_peak':float(scores[day,cell]),
                     'max_score':float(np.max(scores[days,cells])), 'reference_zero_percent_at_peak':float(zeros[day,cell]),
                     'annual_score_at_peak':float(annual[day,cell])})
    write_csv(OUT/'activity_episodes.csv', rows)
    return rows, ids


def event_audit(d, values, scores, zeros, annual, ids):
    records = json.loads((ROOT/'data/processed/perimeters.json').read_text())
    with np.load(ROOT/'data/processed/observations.npz', allow_pickle=False) as obs:
        idx = np.flatnonzero(obs['sensor'] == 1)
        idx = idx[np.argsort(obs['day'][idx], kind='stable')]
        point_day, lat, lon = obs['day'][idx], obs['latitude'][idx], obs['longitude'][idx]
    lookup = {(int(np.floor(y*2)),int(np.floor(x*2))):i for i,(y,x) in enumerate(zip(d['latitude'],d['longitude']))}
    point_cell = np.array([lookup[(int(np.floor(y*2)),int(np.floor(x*2)))] for y,x in zip(lat,lon)])
    rows, skipped = [], Counter()
    for j, record in enumerate(records):
        if record['year'] < 2012:
            continue
        if not record.get('alarm_date_ms') or not record.get('containment_date_ms'):
            skipped['missing_dates'] += 1; continue
        start = datetime.fromtimestamp(record['alarm_date_ms']/1000, tz=timezone.utc).date()
        end = datetime.fromtimestamp(record['containment_date_ms']/1000, tz=timezone.utc).date()
        if not (date(2012,1,20) <= start <= end <= date(2025,12,31)) or (end-start).days > 365:
            skipped['invalid_or_overlong_dates'] += 1; continue
        first, last = (start-EPOCH).days, (end-EPOCH).days
        low, high = np.searchsorted(point_day, [first,last+1])
        geom = shape(record['geometry'])
        if not geom.is_valid:
            skipped['invalid_geometry'] += 1; continue
        west,south,east,north = geom.bounds
        candidates = np.flatnonzero((lon[low:high] >= west) & (lon[low:high] <= east) & (lat[low:high] >= south) & (lat[low:high] <= north)) + low
        prepare(geom)
        matched = candidates[intersects_xy(geom,lon[candidates],lat[candidates])]
        if not len(matched):
            skipped['no_linked_viirs_reports'] += 1; continue
        dates, cells = point_day[matched], point_cell[matched]
        first_report, last_report = int(dates.min()), int(dates.max())
        daily = np.bincount(dates-first_report, minlength=last_report-first_report+1)
        trailing = np.convolve(daily, np.ones(7,dtype=int), mode='full')
        # Windows begin on/after the first report. Center = first report + 3
        # for the first week; select the strongest actual seven-day block for
        # the separate peak diagnostic, never by its anomaly score.
        peak_anchor = first_report + 3 + int(np.argmax(trailing[6:]))
        row = {k:record.get(k) for k in ['id','name','year','area_ha','complex_id','complex_name']}
        row.update(alarm_date=start.isoformat(), containment_date=end.isoformat(), linked_viirs_reports=len(matched),
                   first_report=iso(first_report), last_report=iso(last_report))
        pairs = np.unique(np.column_stack([dates,cells]), axis=0)
        context_scores = scores[pairs[:,0],pairs[:,1]]
        eligible_contexts = np.isfinite(context_scores)
        valid_pairs = pairs[eligible_contexts]
        valid_scores = context_scores[eligible_contexts]
        linked_episodes = np.unique(ids[valid_pairs[:,0],valid_pairs[:,1]])
        linked_episodes = linked_episodes[linked_episodes > 0]
        best_context = int(np.argmax(valid_scores)) if len(valid_scores) else None
        row.update(any_context_score=float(valid_scores.max()) if len(valid_scores) else None,
                   valid_cell_days=len(valid_pairs), outlier_cell_days=int((valid_scores>=95).sum()),
                   maximum_context_anchor=iso(valid_pairs[best_context,0]) if best_context is not None else None,
                   linked_episodes=';'.join(str(int(x)) for x in linked_episodes))
        for prefix, anchor in [('first_week',first_report+3),('peak_week',peak_anchor)]:
            keep = (dates >= anchor-3) & (dates <= anchor+3)
            counts = np.bincount(cells[keep], minlength=len(d['latitude']))
            cell = int(np.argmax(counts))
            def finite(a): return float(a[anchor,cell]) if anchor < len(a) and np.isfinite(a[anchor,cell]) else None
            row.update({f'{prefix}_anchor':iso(anchor),f'{prefix}_cell':cell,
                        f'{prefix}_latitude':float(d['latitude'][cell]), f'{prefix}_longitude':float(d['longitude'][cell]),
                        f'{prefix}_score':finite(scores), f'{prefix}_context_activity':finite(values),
                        f'{prefix}_annual_score':finite(annual), f'{prefix}_reference_zero_percent':finite(zeros),
                        f'{prefix}_fire_reports_in_cell':int(counts[cell]),
                        f'{prefix}_fire_reports_all_cells':int(keep.sum()),
                        f'{prefix}_episode':int(ids[anchor,cell]) if anchor < len(ids) else 0})
        rows.append(row)
        if j % 500 == 0:
            print(f'Perimeter audit {j}/{len(records)}', flush=True)
    write_csv(OUT/'perimeter_associations.csv', rows)
    return rows, dict(skipped)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    with np.load(ROOT/'data/processed/activity_daily.npz', allow_pickle=False) as f:
        d = {key:f[key] for key in f.files}
    values, complete, scores, zeros, annual = window_audit(d)
    usable = np.isfinite(scores)
    active = usable & (values > 0)
    flagged = usable & (scores >= 95)
    summary = {'reference':'VIIRS only', 'measurement_days':WINDOW, 'seasonal_radius_days':RADIUS,
               'first_eligible_anchor':iso(np.flatnonzero(usable.any(axis=1))[0]),
               'last_eligible_anchor':iso(np.flatnonzero(usable.any(axis=1))[-1]),
               'eligible_cell_windows':int(usable.sum()), 'active_cell_windows':int(active.sum()),
               'score_count_spearman_active':float(stats.spearmanr(values[active],scores[active]).statistic),
               'by_activity':[]}
    for threshold in [95,99]:
        flag = usable & (scores >= threshold)
        summary[f'threshold_{threshold}'] = {'windows':int(flag.sum()), 'fraction_all':float(flag.sum()/usable.sum()),
            'fraction_active':float(flag.sum()/active.sum()), 'fraction_activity_le_2':float((values[flag]<=2).mean()),
            'fraction_activity_le_5':float((values[flag]<=5).mean()), 'fraction_reference_zero_ge_95':float((zeros[flag]>=95).mean()),
            'fraction_activity_ge_100':float((values[flag]>=100).mean())}
    for low, high in [(1,1),(2,4),(5,19),(20,99),(100,499),(500,9999999)]:
        keep = active & (values >= low) & (values <= high)
        summary['by_activity'].append({'min':low,'max':high,'windows':int(keep.sum()),
            'flagged_95_fraction':float((scores[keep]>=95).mean()), 'median_score':float(np.median(scores[keep]))})
    for low in [100,500,1000]:
        keep = active & (values >= low)
        summary[f'activity_ge_{low}_not_outlier_fraction'] = float((scores[keep]<95).mean())
    common = active & np.isfinite(annual)
    summary['annual_comparison_active_windows'] = int(common.sum())
    summary['seasonal_added_value'] = {}
    for threshold in [95,99]:
        sf, af = scores[common] >= threshold, annual[common] >= threshold
        summary['seasonal_added_value'][str(threshold)] = {
            'seasonal_only':int((sf & ~af).sum()), 'annual_only':int((~sf & af).sum()),
            'both':int((sf & af).sum()), 'neither':int((~sf & ~af).sum()),
            'seasonal_only_fraction_of_seasonal_flags':float((sf & ~af).sum()/sf.sum())}
    window_rows = []
    for anchor, cell in zip(*np.where(active)):
        window_rows.append({'anchor':iso(anchor),'cell':int(cell),'latitude':float(d['latitude'][cell]),'longitude':float(d['longitude'][cell]),
                            'activity':int(values[anchor,cell]),'score':float(scores[anchor,cell]),
                            'reference_zero_percent':float(zeros[anchor,cell]),
                            'annual_score':float(annual[anchor,cell]) if np.isfinite(annual[anchor,cell]) else None})
    write_csv(OUT/'active_windows.csv.gz', window_rows)
    episode_rows, ids = episodes(d,values,scores,zeros,annual)
    summary['spatiotemporal_episodes'] = len(episode_rows)
    events, skipped = event_audit(d,values,scores,zeros,annual,ids)
    summary['perimeter_associations'] = len(events)
    summary['perimeter_exclusions'] = skipped
    summary['events'] = {}
    for prefix in ['first_week','peak_week']:
        eligible = [r for r in events if r[f'{prefix}_score'] is not None]
        summary['events'][prefix] = {'n':len(eligible),
            'score_area_spearman':float(stats.spearmanr([r['area_ha'] for r in eligible],[r[f'{prefix}_score'] for r in eligible]).statistic),
            'score_activity_spearman':float(stats.spearmanr([r[f'{prefix}_context_activity'] for r in eligible],[r[f'{prefix}_score'] for r in eligible]).statistic),
            'fraction_score_ge_95':float(np.mean([r[f'{prefix}_score']>=95 for r in eligible])),
            'fraction_score_ge_99':float(np.mean([r[f'{prefix}_score']>=99 for r in eligible]))}
        for label,low,high in [('under_100ha',0,100),('100_1000ha',100,1000),('1000_10000ha',1000,10000),('over_10000ha',10000,float('inf'))]:
            group=[r for r in eligible if low<=r['area_ha']<high]
            summary['events'][prefix][label]={'n':len(group),'flagged_95':sum(r[f'{prefix}_score']>=95 for r in group),
                                          'median_score':float(np.median([r[f'{prefix}_score'] for r in group])) if group else None}
    for label,low,high in [('under_100ha',0,100),('100_1000ha',100,1000),('1000_10000ha',1000,10000),('over_10000ha',10000,float('inf'))]:
        group=[r for r in events if r['any_context_score'] is not None and low<=r['area_ha']<high]
        summary['events'].setdefault('any_observed_cell_day',{})[label]={'n':len(group),
            'flagged_95':sum(r['any_context_score']>=95 for r in group),
            'flagged_99':sum(r['any_context_score']>=99 for r in group)}
    associated_episodes={int(x) for r in events for x in r['linked_episodes'].split(';') if x}
    summary['episodes_with_perimeter_association']=len(associated_episodes)
    small = [r for r in events if r['area_ha'] < 100 and r['peak_week_score'] is not None and r['peak_week_score'] >= 95]
    shares = [r['peak_week_fire_reports_in_cell']/r['peak_week_context_activity'] for r in small]
    summary['small_flagged_peak_context'] = {'n':len(small),'median_linked_fire_share':float(np.median(shares)),
                                            'fraction_fire_share_below_half':float(np.mean(np.array(shares)<.5))}
    noncomplex = [r for r in events if not r['complex_id'] and not r['complex_name'] and 'COMPLEX' not in (r['name'] or '').upper() and r['peak_week_score'] is not None]
    summary['noncomplex_peak_sensitivity'] = {'n':len(noncomplex),
        'score_area_spearman':float(stats.spearmanr([r['area_ha'] for r in noncomplex],[r['peak_week_score'] for r in noncomplex]).statistic)}
    assert sum(group['windows'] for group in summary['by_activity']) == summary['active_cell_windows']
    assert len(window_rows) == summary['active_cell_windows']
    for row in events:
        for prefix in ['first_week','peak_week']:
            count = row[f'{prefix}_context_activity']
            assert count is None or row[f'{prefix}_fire_reports_in_cell'] <= count
    summary['input_sha256']={name:hashlib.sha256((ROOT/'data/processed'/name).read_bytes()).hexdigest() for name in ['activity_daily.npz','observations.npz','perimeters.json']}
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
    print(json.dumps(summary,indent=2),flush=True)


if __name__=='__main__':
    main()
