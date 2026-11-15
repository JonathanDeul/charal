"""Count support and reference-leakage regressions for the selected two-stage model."""
import numpy as np
import pandas as pd
import pytest
from backend.harmonization_v4 import OffsetModel,RICH,features
from scripts.train_harmonization_v4 import gate


@pytest.fixture
def frame():
    rng=np.random.default_rng(82);n=480;count=rng.poisson(3,n).astype(float);count[:160]=0
    f=pd.DataFrame({'modis_count':count,'frp_sum':count*10,'frp_mean':np.where(count,10,0),
        'frp_max':count*12,'frp_std':np.zeros(n),'terra_count':count*.5,'day_fraction':np.where(count,.7,0),
        'scan_mean':np.where(count,1.2,0),'track_mean':np.where(count,1.1,0),'footprint_mean':np.where(count,1.32,0),
        'hour_sin':np.zeros(n),'hour_cos':np.zeros(n),'detection_days':np.minimum(count,4),
        'detection_acquisitions':count,'month':np.arange(n)%12+1,'latitude':np.full(n,38.),'longitude':np.full(n,-120.),
        'state':'CA','year':2013+np.arange(n)//120,'viirs_count':rng.poisson(count*3+.4)})
    for col in RICH:f[col]=rng.uniform(0,2,n)
    return f


def test_features_ignore_reference_counts_and_calendar_year(frame):
    original=features(frame)
    changed=features(frame.assign(viirs_count=1e12,year=1900))
    np.testing.assert_array_equal(original,changed)
    assert np.isfinite(original).all()


def test_two_stage_mean_predicts_nonnegative_counts_and_survives_serialization(frame,tmp_path):
    import pickle
    model=OffsetModel('hurdle_rich').fit(frame)
    pred=model.predict(frame)
    assert np.isfinite(pred).all() and (pred>=0).all()
    assert (pred[frame.modis_count.eq(0)]>0).any()
    np.testing.assert_allclose(pred,model.predict(frame.assign(viirs_count=1e9,year=2001)))
    path=tmp_path/'model.pkl'
    with path.open('wb') as f:pickle.dump(model,f)
    with path.open('rb') as f:loaded=pickle.load(f)
    np.testing.assert_array_equal(loaded.predict(frame),pred)


def test_promotion_gate_rejects_aggregate_gain_with_regional_damage():
    baseline={'monthly_mae':100,'cell_month_mae':10,'regions':{'north':{'monthly_mae':50},'south':{'monthly_mae':50}}}
    damaged={'monthly_mae':80,'cell_month_mae':9,'regions':{'north':{'monthly_mae':60},'south':{'monthly_mae':40}}}
    assert not all(gate(damaged,baseline).values())
    good={'monthly_mae':90,'cell_month_mae':9,'regions':{'north':{'monthly_mae':45},'south':{'monthly_mae':45}}}
    assert all(gate(good,baseline).values())
