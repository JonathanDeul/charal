"""Meaningful leakage and count-loss checks for daily contextual research."""
import json
import numpy as np
import pandas as pd
import pytest

torch=pytest.importorskip('torch')
from backend.harmonization_v3 import CountNet,DailyData,metrics


@pytest.fixture
def daily(tmp_path):
    p=tmp_path/'data/research/harmonization_v3';p.mkdir(parents=True)
    processed=tmp_path/'data/processed';processed.mkdir()
    (processed/'perimeters.json').write_text('[]')
    dates=pd.date_range('2013-12-29','2014-01-04')
    pd.DataFrame([{'state':'CA','gy':80,'gx':-240,'latitude':40.25,'longitude':-119.75,'ecoregion':'forest'}]).to_csv(p/'grid.csv',index=False)
    context=np.ones((7,5,5,4),np.float32);local=np.full((7,1,4),2,np.float32)
    np.savez(p/'daily.npz',context=context,local=local,target=np.ones((7,1),np.float32),
        support=np.ones((5,5),bool),date=dates.strftime('%Y-%m-%d').to_numpy(dtype='U10'),
        pair_complete=np.ones(7,bool),context_day_valid=np.ones(7,bool),grid_y=[2],grid_x=[2],gy0=78,gx0=-242)
    return DailyData(tmp_path)


def test_context_excludes_other_split_dates_and_uses_local_center(daily):
    patch,_,_=daily.batch(np.array([2]),[2013,2013],np.ones(12),True)
    raw=patch.reshape(1,7,5,5,5) # day, channel, y, x
    # Target 31 December: the subsequent three days belong to another split.
    assert not raw[0,4:].any()
    assert raw[0,3,4,2,2]==1 # availability for the target day
    np.testing.assert_allclose(raw[0,3,0,2,2],np.log1p(2)/3)
    np.testing.assert_allclose(raw[0,3,0,1,1],np.log1p(1)/3)


def test_reference_labels_cannot_change_context_inputs(daily):
    idx=np.array([1,2,3]);before=daily.batch(idx,[2013,2014],np.ones(12),True)
    daily.target[:]=1e6
    after=daily.batch(idx,[2013,2014],np.ones(12),True)
    for a,b in zip(before,after):np.testing.assert_array_equal(a,b)


def test_known_cross_boundary_fire_purges_training_support(daily):
    daily.events=[{'start':pd.Timestamp('2013-12-30'),'end':pd.Timestamp('2014-01-02'),
        'cells':{0},'ids':['linked-fire'],'missing_dates':False,'area_ha':12000}]
    idx,info=daily.indices([2013,2013],[[2014,2014]])
    assert not len(idx) and info['purged_rows']==3
    assert len(info['crossing_groups'])==1
    valid,_=daily.indices([2014,2014]);assert len(valid)==4


@pytest.mark.parametrize('nb',[False,True])
def test_neural_count_loss_has_finite_gradients_for_zero_and_extreme_counts(nb):
    net=CountNet(3,True,nb)
    x=torch.zeros(4,35,5,5);meta=torch.zeros(4,3)
    mu=net(x,meta,torch.tensor([0.,0.,100.,10000.]))
    y=torch.tensor([0.,4.,500.,20000.])
    loss=net.loss(mu,y).mean();loss.backward()
    assert torch.isfinite(loss) and (mu>0).all()
    assert all(torch.isfinite(p.grad).all() for p in net.parameters() if p.grad is not None)
    if nb:assert net.raw_alpha.grad is not None


def test_monthly_metric_aggregates_daily_predictions_before_scoring():
    f=pd.DataFrame({'month':['2024-01','2024-01'],'cell':[0,0],'latitude':[40.,40.],
        'modis_count':[0.,1.],'viirs_count':[0.,5.]})
    r=metrics(f,np.array([2.,3.]))
    assert r['monthly_mae']==0 and r['cell_daily_mae']==2
    assert r['zero_modis_daily']['bias_total']==2
