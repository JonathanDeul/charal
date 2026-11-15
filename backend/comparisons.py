"""Historical comparisons on the frozen archive; observation counts, not fire severity."""
from datetime import date, timedelta
import numpy as np
from backend.fire_events import project, EPOCH


def compare_years(rows, start, end, reference):
    key = 'viirs_count' if reference == 'viirs' else 'harmonized_count'
    result = []
    for year in range(start, end + 1):
        source = {r['month']: r for r in rows if r['year'] == year}
        values = []
        for month in range(1, 13):
            r = source.get(month, {})
            value = r.get(key)
            if reference == 'viirs' and (year < 2013 or r.get('source') == 'no_grid_coverage' or r.get('viirs_missing_day_count', 0) or r.get('reference_complete') is False):
                value = None
            values.append(value)
        complete = all(v is not None for v in values)
        result.append(dict(year=year, monthly=values, complete=complete,
                           available_months=sum(v is not None for v in values),
                           total=float(sum(values)) if complete else None,
                           modeled=reference == 'harmonized' and any(r.get('source') == 'modeled_modis' for r in source.values())))
    eligible = sorted((r for r in result if r['complete']), key=lambda r: -r['total'])
    for r in result:
        r['rank'] = 1 + sum(x['total'] > r['total'] for x in eligible) if r['complete'] else None
    return dict(years=result, reference=reference, eligible_years=len(eligible), units='satellite detections',
                method='Only 12 eligible months form a ranked annual total. VIIRS annual comparisons start in 2013. Missing months are never zero-filled. No annual uncertainty interval is inferred from monthly bands.')


class FireComparison:
    def __init__(self, scorer):
        self.scorer = scorer
        self.obs = scorer.obs
        self.entries = {}
        for track in scorer.track_slices:
            idx = scorer.members(track)
            idx = idx[self.obs['sensor'][idx] == 1]
            if not len(idx):
                continue
            idx = idx[np.argsort(self.obs['day'][idx], kind='stable')]
            first = int(self.obs['day'][idx[0]])
            if (EPOCH + timedelta(days=first)).year < 2013:
                continue
            meta = scorer.metadata.get(str(track), {})
            associations = meta.get('associations', [])
            self.entries[track] = dict(id=track, label=associations[0]['name'] if associations else f'Observed event {track}',
                                       first=first, idx=idx, xy=scorer.xy[idx[0]])

    def list_events(self, as_of, bounds):
        cutoff = (as_of-EPOCH).days
        w,s,e,n = bounds
        result = []
        for entry in self.entries.values():
            idx = entry['idx']
            recent = idx[(self.obs['day'][idx] <= cutoff) & (self.obs['day'][idx] >= cutoff-6)]
            recent = recent[(self.obs['longitude'][recent] >= w) & (self.obs['longitude'][recent] <= e) &
                            (self.obs['latitude'][recent] >= s) & (self.obs['latitude'][recent] <= n)]
            if len(recent):
                result.append(dict(id=entry['id'], label=entry['label'], recent_detections=int(len(recent)),
                                   first_detection=(EPOCH+timedelta(days=entry['first'])).isoformat(),
                                   latitude=float(self.obs['latitude'][recent].mean()),
                                   longitude=float(self.obs['longitude'][recent].mean())))
        return sorted(result, key=lambda r:(-r['recent_detections'],r['id']))[:100]

    def compare(self, track, as_of):
        entry = self.entries[track]
        cutoff = (as_of-EPOCH).days
        age = cutoff-entry['first']+1
        if not 1 <= age <= 366:
            raise ValueError('Choose a date within the first 366 days after this track’s first detection.')
        valid = self.scorer.activity['viirs_valid']
        def describe(e):
            first = e['first']
            stop = first+age
            if stop > len(valid) or not np.all(valid[first:stop]):
                return None
            idx = e['idx']
            days = self.obs['day'][idx]
            counts = np.bincount(days[(days >= first)&(days < stop)]-first, minlength=age)
            return dict(id=e['id'], label=e['label'], first_detection=(EPOCH+timedelta(days=first)).isoformat(),
                        total=int(counts.sum()), cumulative=np.cumsum(counts).astype(int).tolist())
        target = describe(entry)
        if target is None:
            return dict(status='incomplete_observations', target=None, analogues=[], age_days=age)
        onset = EPOCH+timedelta(days=entry['first'])
        # Use a shared leap-year calendar for circular seasonal distance.
        season = lambda d: (date(2000,d.month,d.day)-date(2000,1,1)).days
        pool = []
        for other in self.entries.values():
            start = EPOCH+timedelta(days=other['first'])
            # All comparison days precede the target's onset year.
            if other['first']+age > (date(onset.year,1,1)-EPOCH).days:
                continue
            distance = float(np.linalg.norm(other['xy']-entry['xy']))
            delta = abs(season(start)-season(onset))
            delta = min(delta,366-delta)
            if distance > 300 or delta > 60:
                continue
            r = describe(other)
            if r is not None:
                r.update(distance_km=round(distance,1), season_distance_days=delta)
                a = np.log1p(target['cumulative'])
                b = np.log1p(r['cumulative'])
                r['similarity_distance'] = float(np.mean(np.abs(a-b)))
                pool.append(r)
        rank = float(100*np.mean([float(r['total'] < target['total'])+.5*(r['total']==target['total']) for r in pool])) if pool else None
        analogues = sorted(pool,key=lambda r:(r['similarity_distance'],r['id']))[:5]
        return dict(status='ok', target=target, age_days=age, as_of=as_of.isoformat(), reference_events=len(pool),
                    reference_years=sorted({int(r['first_detection'][:4]) for r in pool}), percentile=rank,
                    analogues=analogues, method='Observed Suomi-NPP VIIRS tracks starting in 2013–2025. Same number of UTC days since first detection; prior years only; onset within ±60 seasonal days and 300 projected km. Five examples minimize mean absolute log1p cumulative-count difference. Rank uses all eligible tracks, not just the examples. Known-gap windows excluded.',
                    limitations='Tracks may merge or split fires and use full-archive connectivity; this is a retrospective comparison, not a reconstructed live incident identity. Names are retrospective CAL FIRE associations. First detection is not ignition. Zero reports do not prove inactivity. No burned area or danger is inferred.')
