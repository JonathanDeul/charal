"""Observed activity events and two-part seasonal outlier descriptions.

Event identities are inferred connected components, not verified incidents.
First observed regional activity is always retained as an occurrence outlier.
Reference support describes uncertainty without attenuating that novelty.
"""
from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree

from backend.anomalies import EPOCH, rolling, reference_weights

RADIUS_KM = 10.
LINK_KM = 3.
LINK_DAYS = 2
SWITCH = (date(2012, 2, 1) - EPOCH).days
EARTH_KM = 6371.0088
COS0 = np.cos(np.deg2rad(37.5))


def project(latitude, longitude):
    return np.column_stack([EARTH_KM * COS0 * np.deg2rad(longitude),
                            EARTH_KM * np.sin(np.deg2rad(latitude)) / COS0])


def inverse_project(x, y):
    return float(np.rad2deg(np.arcsin(y * COS0 / EARTH_KM))), float(np.rad2deg(x / (EARTH_KM * COS0)))


def cluster_detections(days, sensor, xy):
    """Link occupied 1 km cells within 3 km / two days; retain single reports."""
    nodes, inverse = np.unique(np.column_stack([sensor, days, np.floor(xy).astype(int)]), axis=0, return_inverse=True)
    labels = np.empty(len(nodes), dtype=np.int32)
    offset = 0
    for source in np.unique(sensor):
        selected = np.flatnonzero(nodes[:,0] == source)
        current = nodes[selected]
        coords = np.column_stack([current[:,2:4], current[:,1] * LINK_KM / LINK_DAYS])
        pairs = cKDTree(coords).query_pairs(LINK_KM, p=np.inf, output_type='ndarray')
        if len(pairs):
            delta = current[pairs[:,0],2:4] - current[pairs[:,1],2:4]
            pairs = pairs[(delta*delta).sum(axis=1) <= LINK_KM**2]
        graph = coo_matrix((np.ones(len(pairs),dtype=np.uint8),(pairs[:,0],pairs[:,1])), shape=(len(current),len(current)))
        count, components = connected_components(graph, directed=False)
        labels[selected] = components + offset + 1
        offset += count
    return labels[inverse]


def window_event_max(days, tracks, amounts, n_days, window):
    """Largest single-event total, not the sum of neighboring events."""
    result = np.zeros(n_days)
    if not len(days):
        return result
    order = np.argsort(tracks, kind='stable')
    groups = np.split(order, np.flatnonzero(np.diff(tracks[order]))+1)
    for group in groups:
        dates = days[group].astype(int)
        first = int(dates.min())
        counts = np.bincount(dates-first, weights=amounts[group])
        sums = np.convolve(counts, np.ones(window), mode='full')
        start = first - window//2
        low, high = max(0,start), min(n_days,start+len(sums))
        result[low:high] = np.maximum(result[low:high], sums[low-start:high-start])
    return result


def two_part(values, weights, years, target, first_recorded=False):
    """Empirical hurdle decomposition; absence is not physical fire absence."""
    keep = weights > 0
    if target <= 0:
        return None
    if not keep.any():
        return {'occurrence_score':100.,'seasonal_zero_percent':None,'activity_score_local':None,
                'active_reference_years':[],'positive_reference_windows':0,'first_recorded':True,
                'no_seasonal_activity':None} if first_recorded else None
    v, w = values[keep], weights[keep]
    positive = v > 0
    zero_fraction = float(w[~positive].sum()/w.sum())
    active_years = np.unique(years[keep][positive]).astype(int).tolist()
    strength = None
    if positive.any():
        p, pw = v[positive], w[positive]
        ties = np.isclose(p,target,rtol=1e-10,atol=1e-8)
        strength = float(100 * np.sum(pw*(((p < target)&~ties)+.5*ties)) / pw.sum())
    return {'occurrence_score':100. if first_recorded else 100*zero_fraction,
            'seasonal_zero_percent':100*zero_fraction, 'activity_score_local':strength,
            'active_reference_years':active_years, 'positive_reference_windows':int(positive.sum()),
            'first_recorded':bool(first_recorded), 'no_seasonal_activity':not bool(positive.any())}


def combine_strength(local, regional):
    """Borrow positive-count ranks only; never shrink occurrence novelty."""
    support = len(local['active_reference_years'])
    estimates = [r['activity_score_local'] for r in regional if r and r['activity_score_local'] is not None]
    own = local['activity_score_local']
    borrowed = float(np.mean(estimates)) if estimates else None
    mixing = max(0., (3-support)/3) if borrowed is not None else 0.
    if own is None:
        value, mixing = borrowed, 1. if borrowed is not None else 0.
    else:
        value = (1-mixing)*own + mixing*borrowed if borrowed is not None else own
    return value, mixing


class EventScorer:
    def __init__(self, observations, activity, tracks, metadata):
        if len(tracks) != len(observations['day']):
            raise ValueError('Event artifact does not match packed observations')
        self.obs, self.activity, self.tracks, self.metadata = observations, activity, tracks, metadata
        self.xy = project(observations['latitude'].astype(float), observations['longitude'].astype(float))
        self.tree = cKDTree(self.xy)
        self.by_day = np.argsort(observations['day'],kind='stable')
        self.sorted_days = observations['day'][self.by_day]
        self.by_track = np.argsort(tracks,kind='stable')
        unique, starts = np.unique(tracks[self.by_track],return_index=True)
        self.track_slices = {int(k):(int(a),int(b)) for k,a,b in zip(unique,starts,np.r_[starts[1:],len(tracks)])}

    def members(self, track):
        start, stop = self.track_slices[int(track)]
        return self.by_track[start:stop]

    def source_mask(self, indices, reference):
        source, days = self.obs['sensor'][indices], self.obs['day'][indices]
        return source == 1 if reference == 'viirs' else ((source == 0)&(days < SWITCH)) | ((source == 1)&(days >= SWITCH))

    @lru_cache(maxsize=512)
    def nearby(self, x, y):
        return np.asarray(self.tree.query_ball_point([x,y],RADIUS_KM),dtype=int)

    def describe_event(self, track, anchor, window, radius, reference, threshold):
        obs, a = self.obs, self.activity
        members = self.members(track)
        selected = members[self.source_mask(members,reference)]
        current = selected[(obs['day'][selected] >= anchor-(window-1)//2)&(obs['day'][selected] <= anchor+window//2)]
        if not len(current):
            return None
        # Use the densest occupied 1 km cell in the target window. Its fixed
        # center is independent of future spread and stable under report order.
        cells, counts = np.unique(np.floor(self.xy[current]).astype(int),axis=0,return_counts=True)
        center = cells[np.argmax(counts)] + .5
        x, y = float(center[0]), float(center[1])
        nearby = self.nearby(x,y)
        nearby = nearby[self.source_mask(nearby,reference)]
        local_current = current[np.linalg.norm(self.xy[current]-center,axis=1) <= RADIUS_KM]
        target_years = np.unique(a['years'][max(0,anchor-(window-1)//2):anchor+window//2+1])
        ratios = a['ratios']
        if 'ratios_by_year' in a:
            ratios = a['ratios_by_pair'][int(target_years[0])-2001] if len(target_years)>1 else a['ratios_by_year'][int(target_years[0])-2001]
        def amounts(indices):
            return np.where(obs['sensor'][indices] == 1,1.,ratios[a['season'][obs['day'][indices]]])
        target = float(amounts(local_current).sum())
        valid = a['viirs_valid'] if reference == 'viirs' else np.where(np.arange(len(a['years'])) >= SWITCH,a['viirs_valid'],a['modis_valid'])
        _, complete = rolling(np.zeros((len(valid),1)),valid,window)
        if not complete[anchor]:
            return None
        # Exclude every report date of the same inferred event, including its
        # appearances in adjacent years, from reference measurement support.
        ref_valid = valid.copy()
        ref_valid[obs['day'][selected]] = False
        _, ref_complete = rolling(np.zeros((len(valid),1)),ref_valid,window)
        reference_points = nearby[self.tracks[nearby] != track]
        local_values = window_event_max(obs['day'][reference_points],self.tracks[reference_points],amounts(reference_points),len(valid),window)
        local_event_points = nearby[self.tracks[nearby] == track]
        onset = int(obs['day'][local_event_points].min())
        # Genuine archive novelty is retained even if later years contain other
        # fires. The seasonal rank remains separately available for inspection.
        # A retained positive report is evidence of earlier activity even on a
        # listed incomplete day. Exposure gaps invalidate frequency windows,
        # but must not erase a real observation and manufacture novelty.
        prior = reference_points[obs['day'][reference_points] < onset]
        first_recorded = not bool(len(prior))
        first_valid = int(np.flatnonzero(valid)[0])
        earlier_years = max(0.,(onset-first_valid)/365.25)

        regional_values = []
        def components(season_radius):
            weights, years = reference_weights(a['years'],a['season'],ref_complete,anchor,window,season_radius)
            local = two_part(local_values,weights,a['years'],target,first_recorded)
            if local is None:
                return None, years, weights
            return local, years, weights
        local, years, weights = components(radius)
        if local is None:
            return None
        if len(local['active_reference_years']) < 3:
            for dx,dy in [(30,0),(-30,0),(0,30),(0,-30)]:
                points = self.nearby(x+dx,y+dy)
                points = points[self.source_mask(points,reference)&(self.tracks[points] != track)]
                regional_values.append(window_event_max(obs['day'][points],self.tracks[points],amounts(points),len(valid),window))
        regional = [two_part(v,weights,a['years'],target) for v in regional_values]
        strength, mixing = combine_strength(local,regional)
        reasons = []
        if local['occurrence_score'] >= threshold:
            reasons.append('first_recorded_activity' if first_recorded else 'rare_occurrence')
        if strength is not None and strength >= threshold:
            reasons.append('unusual_activity')
        sensitivity = []
        for alternative in sorted({max(15,radius//2),min(60,int(radius*1.5))}-{radius}):
            other, _, w = components(alternative)
            if other:
                score,_ = combine_strength(other,[two_part(v,w,a['years'],target) for v in regional_values])
                sensitivity.append({'season_days':alternative,'occurrence_score':round(other['occurrence_score'],2),
                                    'activity_score':round(score,2) if score is not None else None})
        stable = all((s['occurrence_score'] >= threshold)==(local['occurrence_score']>=threshold) and
                     ((s['activity_score'] is not None and s['activity_score']>=threshold)==(strength is not None and strength>=threshold)) for s in sensitivity)
        lat,lon = inverse_project(x,y)
        b = [float(obs['longitude'][current].min()),float(obs['latitude'][current].min()),
             float(obs['longitude'][current].max()),float(obs['latitude'][current].max())]
        meta = self.metadata.get(str(int(track)),{})
        associations = meta.get('associations',[])
        return {'id':int(track),'label':associations[0]['name'] if associations else f'Observed event {int(track)}',
                'associations':associations[:3], 'sensor':'VIIRS' if obs['sensor'][current[0]] else 'MODIS',
                'latitude':lat,'longitude':lon,'bounds':b,'comparison_radius_km':RADIUS_KM,
                'observations':int(len(current)),'scored_observations':int(len(local_current)),
                'activity':round(target,2),'occurrence_score':round(local['occurrence_score'],2),
                'seasonal_occurrence_score':round(local['seasonal_zero_percent'],2) if local['seasonal_zero_percent'] is not None else None,
                'activity_score':round(strength,2) if strength is not None else None,
                'local_activity_score':round(local['activity_score_local'],2) if local['activity_score_local'] is not None else None,
                'first_recorded':first_recorded,'no_seasonal_activity':local['no_seasonal_activity'],
                'prior_observed_years':round(earlier_years,1),'reference_years':years,
                'active_reference_years':local['active_reference_years'],
                'positive_reference_windows':local['positive_reference_windows'],
                'regional_activity_weight':round(mixing,3),'regional_reference_areas':len(regional_values),
                'support':'limited' if earlier_years<3 or len(local['active_reference_years'])<3 else 'broader',
                'season_sensitive':not stable,'sensitivity':sensitivity,'outlier':bool(reasons),'reasons':reasons,
                'first_detection':(EPOCH+timedelta(days=int(obs['day'][selected].min()))).isoformat(),
                'last_detection':(EPOCH+timedelta(days=int(obs['day'][selected].max()))).isoformat()}

    def score(self, anchor_date, window=7, radius=30, reference='viirs',threshold=95.,bounds=(-124.5,32.5,-114.1,42.1), include_points=False):
        anchor = (anchor_date-EPOCH).days
        low, high = np.searchsorted(self.sorted_days,[anchor-(window-1)//2,anchor+window//2+1])
        indices = self.by_day[low:high]
        w,s,e,n = bounds
        keep = self.source_mask(indices,reference)&(self.obs['longitude'][indices]>=w)&(self.obs['longitude'][indices]<=e)&(self.obs['latitude'][indices]>=s)&(self.obs['latitude'][indices]<=n)
        tracks = np.unique(self.tracks[indices[keep]])
        valid = self.activity['viirs_valid'] if reference=='viirs' else np.where(np.arange(len(self.activity['years']))>=SWITCH,self.activity['viirs_valid'],self.activity['modis_valid'])
        _, complete = rolling(np.zeros((len(valid),1)),valid,window)
        status = 'ok' if complete[anchor] else 'incomplete_observations'
        events = [self.describe_event(int(track),anchor,window,radius,reference,threshold) for track in tracks] if status=='ok' else []
        unavailable = sum(event is None for event in events)
        events = [event for event in events if event is not None]
        result = {'schema_version':2,'status':status,'anchor_date':anchor_date.isoformat(),
                  'start_date':(anchor_date-timedelta(days=(window-1)//2)).isoformat(),
                  'end_date':(anchor_date+timedelta(days=window//2)).isoformat(),
                  'window_days':window,'season_days':radius,'reference':reference,'threshold':threshold,
                  'events':events,'events_total':len(tracks),'events_unavailable':unavailable,
                  'outlier_events':sum(event['outlier'] for event in events),
                  'first_recorded_events':sum(event['first_recorded'] for event in events),
                  'points':[], 'method':{
                      'tracking':'Connected occupied 1 km cells: at most 3 km between cell centers and two UTC days; separate sensors; single reports retained.',
                      'occurrence':'Year-balanced seasonal fraction of empty comparison windows. First recorded regional events retain score 100, regardless of support or regional pooling.',
                      'activity':'Conditional positive-count rank against the largest single historical event in the same 10 km comparison area and same measurement duration.',
                      'regional_support':'Only activity strength borrows from four equally sized comparison areas 30 km away when fewer than three local active years exist. Weight=(3-active years)/3; no occurrence pooling.',
                      'novelty':'No earlier retained observation from another inferred event inside the same 10 km area, in the selected sensor archive. This does not establish absence of pre-archive fires.',
                      'exclusion':'Whole target measurement years and every reference window overlapping the same inferred event are excluded.',
                      'outlier':'Either occurrence or activity exceeds the threshold; component scores and reasons remain separate. This is not a calibrated combined probability.',
                      'support':'Reference support and seasonal-window sensitivity describe reliability without reducing novelty or suppressing first recorded events.'}}
        if include_points:
            selected_ids = {event['id'] for event in events}
            for i in indices:
                if int(self.tracks[i]) in selected_ids and self.source_mask(np.array([i]),reference)[0]:
                    result['points'].append([float(self.obs['latitude'][i]),float(self.obs['longitude'][i]),int(self.tracks[i])])
        return result
