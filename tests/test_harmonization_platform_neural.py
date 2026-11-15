import pytest
torch=pytest.importorskip('torch')
from backend.harmonization_platform_neural import PlatformFusionNet
from backend.harmonization_v7 import conditional_loss


@pytest.mark.parametrize('architecture',['platform_mlp','platform_transformer'])
def test_platform_fusion_initial_mean_and_gradients(architecture):
    torch.manual_seed(42);net=PlatformFusionNet(3,2,architecture)
    x=torch.randn(2,4,7);base=torch.tensor([[[0.,0.],[1.,2.],[3.,4.],[10.,20.]],[[0.,1.],[2.,0.],[4.,5.],[0.,0.]]])
    has=(base.sum(-1)>0).float();mu,logit,pos=net(x,base,has,torch.zeros(2,4,8,20))
    expected=1+base.mean(-1)+torch.nn.functional.softplus(torch.tensor(-3.))
    torch.testing.assert_close(pos,expected)
    assert (pos>=1).all() and torch.isfinite(mu).all()
    y=torch.tensor([[0.,5.,10.,80.],[3.,0.,15.,1.]])
    loss=conditional_loss(mu,logit,pos,y,torch.tensor([True,True,False,False]),.05);loss.backward()
    assert torch.isfinite(loss) and all(torch.isfinite(p.grad).all() for p in net.parameters() if p.grad is not None)
