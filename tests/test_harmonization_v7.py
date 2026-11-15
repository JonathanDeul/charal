import pytest
torch=pytest.importorskip('torch')
from backend.harmonization_v7 import EmbeddedHurdle,conditional_loss


@pytest.mark.parametrize('architecture',['raw','plr_mlp','feature_transformer'])
def test_embedded_neural_hurdle_preserves_count_support(architecture):
    torch.manual_seed(41);knots=torch.linspace(-2,2,9).repeat(4,1)
    net=EmbeddedHurdle(4,architecture,knots)
    x=torch.randn(2,4,4);base=torch.tensor([[0.,1.,2.,3.],[0.,0.,10.,100.]])
    mu,logit,positive=net(x,base,(base>0).float(),torch.zeros(2,4,8,20))
    assert torch.isfinite(mu).all() and (mu>0).all() and (positive>=1).all()
    y=torch.tensor([[0.,3.,5.,2.],[1.,0.,20.,300.]])
    loss=conditional_loss(mu,logit,positive,y,torch.tensor([True,True,False,False]),.05)
    loss.backward();assert torch.isfinite(loss)
    assert all(torch.isfinite(p.grad).all() for p in net.parameters() if p.grad is not None)


def test_conditional_loss_accepts_empty_activity_batch():
    mu=torch.ones(2,4,requires_grad=True);logit=torch.zeros_like(mu);positive=torch.ones_like(mu)*2
    loss=conditional_loss(mu,logit,positive,torch.zeros_like(mu),torch.tensor([True,True,False,False]),.05)
    loss.backward();assert torch.isfinite(loss) and torch.isfinite(mu.grad).all()
