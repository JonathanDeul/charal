import pytest
torch=pytest.importorskip('torch')
from backend.harmonization_v6 import RegionalCountNet


@pytest.mark.parametrize('architecture',['pool_fixed','attention_fixed','attention_flexible'])
def test_regional_neural_models_are_finite_and_permutation_equivariant(architecture):
    torch.manual_seed(7);north=torch.tensor([True,False,True,False])
    model=RegionalCountNet(5,architecture,north).eval()
    x=torch.randn(2,4,5);base=torch.tensor([[1.,2.,3.,4.],[0.,4.,5.,0.]])
    has=(base>0).float();temporal=torch.zeros(2,4,8,20)
    mu,_=model(x,base,has,temporal);mu.sum().backward()
    assert torch.isfinite(mu).all() and (mu>0).all()
    assert all(torch.isfinite(p.grad).all() for p in model.parameters() if p.grad is not None)
    order=torch.tensor([2,0,3,1]);other=RegionalCountNet(5,architecture,north[order]).eval()
    other.load_state_dict(model.state_dict())
    with torch.no_grad():permuted,_=other(x[:,order],base[:,order],has[:,order],temporal[:,order])
    torch.testing.assert_close(permuted,mu.detach()[:,order],rtol=1e-5,atol=1e-5)


def test_fixed_allocation_preserves_relative_baseline_shares_within_region():
    model=RegionalCountNet(3,'pool_fixed',torch.tensor([True,True,False,False])).eval()
    x=torch.randn(1,4,3);base=torch.tensor([[2.,4.,3.,9.]])
    with torch.no_grad():mu,_=model(x,base,torch.ones_like(base),torch.zeros(1,4,8,20))
    torch.testing.assert_close((mu[0,1]-1e-6)/(mu[0,0]-1e-6),torch.tensor(2.))
    torch.testing.assert_close((mu[0,3]-1e-6)/(mu[0,2]-1e-6),torch.tensor(3.))
