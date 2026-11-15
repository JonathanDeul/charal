"""Pure neural count support, attention equivariance, and objective regressions."""
import numpy as np
import pytest
torch=pytest.importorskip('torch')
from backend.harmonization_v5 import NeuralHurdle,joint_loss


@pytest.mark.parametrize('architecture',['mlp','spatial','temporal'])
def test_neural_count_outputs_and_gradients_are_finite(architecture):
    torch.manual_seed(17)
    model=NeuralHurdle(6,architecture)
    x=torch.randn(2,4,6);base=torch.tensor([[0.,1.,50.,1000.],[0.,0.,100.,10.]])
    has=(base>0).float();temporal=torch.randn(2,4,8,20)
    mu,logit=model(x,base,has,temporal)
    y=torch.tensor([[0.,3.,120.,2000.],[2.,0.,400.,20.]])
    loss=joint_loss(mu,logit,y,torch.tensor([True,True,False,False]),.05)
    loss.backward()
    assert (mu>0).all() and torch.isfinite(loss)
    assert all(torch.isfinite(p.grad).all() for p in model.parameters() if p.grad is not None)


def test_spatial_attention_respects_cell_permutations():
    torch.manual_seed(19);model=NeuralHurdle(5,'spatial').eval()
    # Give the attention trunk nonzero influence (the training initializer
    # intentionally begins at the seasonal reference).
    torch.nn.init.normal_(model.head.weight,std=.02)
    x=torch.randn(2,5,5);base=torch.rand(2,5)*10;has=torch.ones_like(base);t=torch.randn(2,5,8,20)
    order=torch.tensor([3,0,4,2,1])
    with torch.no_grad():
        original,_=model(x,base,has,t)
        permuted,_=model(x[:,order],base[:,order],has[:,order],t[:,order])
    torch.testing.assert_close(permuted,original[:,order],rtol=1e-5,atol=1e-5)


def test_aggregate_loss_detects_regional_cancellation():
    y=torch.tensor([[0.,10.]])
    perfect=torch.tensor([[.01,9.99]])
    shifted=torch.tensor([[5.,5.]])
    logits=torch.zeros_like(y);north=torch.tensor([True,False])
    # Statewide totals are equal, but a transfer between north/south must be
    # penalized even if the local Poisson term is disabled.
    assert joint_loss(shifted,logits,y,north,0)>joint_loss(perfect,logits,y,north,0)
