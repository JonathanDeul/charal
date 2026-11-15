import numpy as np
import pandas as pd
import torch
from backend.harmonization_v9 import SeasonalReference,SpaceTimeTransformer,location_encoding,count_loss


def test_seasonal_reference_excludes_own_year_and_all_holdout_targets():
    f=pd.DataFrame({'year':[2013,2014,2021],'month':[7]*3,'gy':[70]*3,'gx':[-240]*3,'modis_count':[10.,100.,9999.],'frp_sum':[20.,200.,9999.]})
    ref=SeasonalReference().fit(f.iloc[:2]);out=ref.transform(f)
    np.testing.assert_allclose(out[0,0],np.log1p(100),rtol=1e-6)
    np.testing.assert_allclose(out[1,0],np.log1p(10),rtol=1e-6)
    np.testing.assert_allclose(out[2,0],(np.log1p(10)+np.log1p(100))/2,rtol=1e-6)
    mutated=f.copy();mutated.loc[2,['modis_count','frp_sum']]=1
    np.testing.assert_array_equal(out,ref.transform(mutated))


def test_location_encoding_is_continuous_and_distinguishes_sites():
    a=location_encoding(np.array([37.,37.00001,38.]),np.array([-120.,-120.,-120.]))
    assert a.shape==(3,22)
    assert np.max(np.abs(a[0]-a[1]))<.001
    assert not np.allclose(a[0],a[2])


def test_masked_context_cannot_affect_predictions_and_empty_context_is_finite():
    torch.manual_seed(42)
    net=SpaceTimeTransformer(4,width=16,temporal_layers=1,spatial_layers=1,heads=2,dropout=0).eval()
    # Nonzero head ensures the test measures context, not just initialization.
    torch.nn.init.normal_(net.head[-1].weight,std=.1)
    b={'daily':torch.randn(2,9,7,9),'valid':torch.ones(2,9,7,dtype=torch.bool),
       'location':torch.randn(2,9,26),'static':torch.randn(2,4),'normal':torch.randn(2,5),'base':torch.tensor([0.,100.])}
    b['valid'][:,:,5:]=False;b['valid'][1]=False
    with torch.no_grad():
        first=net(b)[0]
        b['daily'][:,:,5:]=1e5
        second=net(b)[0]
    torch.testing.assert_close(first,second)
    assert torch.isfinite(first).all() and (first>=0).all()
    loss=count_loss(first,torch.zeros(2),first+1,torch.tensor([0.,10.]))
    assert torch.isfinite(loss)


def test_context_crosses_year_boundary_and_preserves_gap_and_support_masks():
    from backend.harmonization_v9 import ContextData
    d=ContextData.__new__(ContextData)
    d.dates=['2020-12-01'];d.C=1;d.radius=1;d.halo=3;d._cache={}
    d.cells=pd.DataFrame({'gy':[70],'gx':[-240],'latitude':[35.25],'longitude':[-119.75]})
    d.offsets=np.array([(y,x) for y in [-1,0,1] for x in [-1,0,1]])
    d.y0=69;d.x0=-241;d.support=np.ones((3,3),bool);d.support[0,0]=False
    d.daily_dates=pd.date_range('2020-12-28','2021-01-03')
    d.daily=np.ones((7,3,3,4),np.float32);d.day_valid=np.ones(7,bool);d.day_valid[2]=False
    x,valid,location=d.context(0)
    assert x.shape==(1,9,37,9) and location.shape==(1,9,26)
    assert valid[0,4,-1]  # Jan3 is included in December's retrospective halo.
    assert x[0,4,-1,7]==0  # Halo day is outside target month.
    assert not valid[0,4,32]  # Dec30 source outage.
    assert not valid[0,0].any()  # No geographic support.
    assert not valid[0,4,0]  # Missing archive date is not a measured zero.
    assert location[0,4,24]==0 and location[0,4,25]==1
