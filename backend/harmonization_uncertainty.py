"""Empirical aggregate residual bands, without unsupported historical guarantees."""
import math
import numpy as np
import pandas as pd


def empirical_rank_quantile(values,level):
    """Conservative finite-sample rank; unavailable when requested rank exceeds n.

    This rank convention alone does not confer coverage under time dependence,
    historical distribution shift, or repeated model selection.
    """
    x=np.asarray(values,float)
    if not 0<level<1:raise ValueError('Level must lie strictly between0 and1')
    if not len(x) or not np.isfinite(x).all() or (x<0).any():raise ValueError('Invalid residual scores')
    rank=math.ceil((len(x)+1)*level)
    return None if rank>len(x) else float(np.sort(x)[rank-1])


def aggregate(frame,prediction):
    f=frame[['date','latitude','viirs_count']].copy();f['prediction']=np.asarray(prediction,float)
    result={}
    for region,mask in [('state',np.ones(len(f),bool)),('north',f.latitude.to_numpy()>=39.5),('south',f.latitude.to_numpy()<39.5)]:
        if not mask.any():continue
        g=f[mask].groupby('date')[['viirs_count','prediction']].sum(min_count=1).reset_index()
        result[region]=g
    return result


def fit_bands(frame,prediction,levels=(.8,.95),scale_power=.5):
    if not 0<=scale_power<=1:raise ValueError('Invalid scale power')
    calibration={'method':'Empirical aggregate residual rank bands','scale_power':scale_power,'levels':list(levels),'regions':{},
        'interpretation':'Disagreement with the SNPP reporting scale, not uncertainty about true fires or burned area.',
        'guarantee':'No guaranteed coverage under temporal dependence, historical shift, or repeated historical model development.',
        'cell_warning':'Aggregate bands are fitted after aggregation. Do not sum cell intervals.',
        'history_warning':'Terra-only and other unsupported historical regimes require separate sensitivity flags; band width does not fully quantify extrapolation bias.'}
    for region,g in aggregate(frame,prediction).items():
        if g.viirs_count.isna().any():raise ValueError('Calibration targets must be available')
        scale=np.power(g.prediction.to_numpy()+1,scale_power)
        scores=np.abs(g.viirs_count.to_numpy()-g.prediction.to_numpy())/scale
        calibration['regions'][region]={'n_months':len(g),'dates':g.date.tolist(),
            'quantiles':{str(level):empirical_rank_quantile(scores,level) for level in levels}}
    return calibration


def band_bounds(prediction,calibration,region='state',level=.8):
    p=np.asarray(prediction,float)
    if not np.isfinite(p).all() or (p<0).any():raise ValueError('Predictions must be finite nonnegative counts')
    q=calibration['regions'][region]['quantiles'][str(level)]
    if q is None:return None,None
    width=q*np.power(p+1,calibration['scale_power'])
    return np.maximum(p-width,0),p+width


def evaluate_bands(frame,prediction,calibration):
    result={}
    for region,g in aggregate(frame,prediction).items():
        by_level={}
        for level in calibration['levels']:
            low,high=band_bounds(g.prediction.to_numpy(),calibration,region,level)
            if low is None:by_level[str(level)]={'available':False};continue
            actual=g.viirs_count.to_numpy()
            # Aggregation order can move an endpoint by a few floating-point
            # units. A calibration residual exactly at the chosen rank stays
            # inside its closed interval after a row-order change.
            inside=((actual>=low)|np.isclose(actual,low,rtol=1e-12,atol=1e-9))&((actual<=high)|np.isclose(actual,high,rtol=1e-12,atol=1e-9))
            by_level[str(level)]={'available':True,'months':len(g),'covered':int(inside.sum()),'coverage':float(inside.mean()),
                'mean_width':float((high-low).mean()),'monthly':[{'date':d,'actual':float(y),'predicted':float(p),'lower':float(l),'upper':float(u),'covered':bool(c)} for d,y,p,l,u,c in zip(g.date,actual,g.prediction,low,high,inside)]}
        result[region]=by_level
    return result
