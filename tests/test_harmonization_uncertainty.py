import numpy as np
import pandas as pd
import pytest
from backend.harmonization_uncertainty import empirical_rank_quantile,fit_bands,band_bounds,evaluate_bands


def test_rank_quantile_is_explicit_about_insufficient_sample():
    assert empirical_rank_quantile(np.arange(1,21),.8)==17
    assert empirical_rank_quantile(np.arange(1,21),.95)==20
    assert empirical_rank_quantile(np.arange(1,11),.95) is None


def test_bands_are_fitted_after_aggregation_and_not_summed_from_cells():
    dates=pd.date_range('2020-01-01',periods=20,freq='MS').strftime('%Y-%m-%d')
    f=pd.DataFrame({'date':np.repeat(dates,2),'latitude':np.tile([40.,37.],20),'viirs_count':np.tile([2.,8.],20)})
    # Local errors cancel completely for statewide totals, but regional bands
    # retain each region's disagreement.
    p=np.tile([4.,6.],20);cal=fit_bands(f,p)
    state=cal['regions']['state']['quantiles']['0.8'];assert state==0
    assert cal['regions']['north']['quantiles']['0.8']>0
    assessment=evaluate_bands(f,p,cal);assert assessment['state']['0.8']['coverage']==1
    lo,hi=band_bounds(np.array([0.,10.]),cal,'north',.8);assert (lo>=0).all() and (hi>=lo).all()


def test_missing_reference_is_not_a_zero_calibration_target():
    f=pd.DataFrame({'date':['2020-01-01'],'latitude':[40.],'viirs_count':[np.nan]})
    with pytest.raises(ValueError,match='available'):fit_bands(f,[0.])


def test_closed_band_endpoint_survives_floating_point_aggregation():
    f=pd.DataFrame({'date':['2020-01-01'],'latitude':[40.],'viirs_count':[10.]})
    # A closed upper endpoint can round a few units below the reference.
    cal={'levels':[.8],'scale_power':0.,'regions':{
        region:{'quantiles':{'0.8':1.-2e-15}} for region in ['state','north']}}
    result=evaluate_bands(f,[9.],cal)
    assert result['state']['0.8']['covered']==1
