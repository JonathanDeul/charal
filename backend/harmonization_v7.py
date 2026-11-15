"""Numeric embeddings and per-cell feature attention for neural count means."""
import torch
from torch import nn
from torch.nn import functional as F


class EmbeddedHurdle(nn.Module):
    def __init__(self,n_features,architecture,knots):
        super().__init__();self.architecture=architecture
        self.register_buffer('knots',knots)
        if architecture=='raw':width=n_features
        else:
            dim=16 if architecture=='feature_transformer' else 8
            self.embedding=nn.Parameter(torch.randn(n_features,8,dim)*.03)
            self.feature_bias=nn.Parameter(torch.randn(n_features,dim)*.02)
            width=n_features*dim
            if architecture=='feature_transformer':
                self.cls=nn.Parameter(torch.zeros(1,1,16))
                layer=nn.TransformerEncoderLayer(16,2,dim_feedforward=32,dropout=.1,batch_first=True,norm_first=True,activation='gelu')
                self.attention=nn.TransformerEncoder(layer,2,enable_nested_tensor=False);width=16
        self.decoder=nn.Sequential(nn.Linear(width,64),nn.ReLU(),nn.Dropout(.1),nn.Linear(64,64),nn.ReLU(),nn.Dropout(.1),nn.Linear(64,3))
        nn.init.zeros_(self.decoder[-1].weight);self.decoder[-1].bias.data[:]=torch.tensor([0.,-3.,0.])

    def forward(self,x,base,has,temporal):
        if self.architecture=='raw':h=x
        else:
            lo=self.knots[:,:-1];hi=self.knots[:,1:]
            basis=((x[:,:,:,None]-lo)/(hi-lo).clamp_min(1e-3)).clamp(0,1)
            embedded=torch.einsum('bcfk,fkd->bcfd',basis,self.embedding)+self.feature_bias
            if self.architecture=='feature_transformer':
                b,c,f,d=embedded.shape;tokens=embedded.reshape(b*c,f,d)
                tokens=torch.cat([self.cls.expand(b*c,-1,-1),tokens],dim=1)
                h=self.attention(tokens)[:,0].reshape(b,c,16)
            else:h=embedded.flatten(-2)
        out=self.decoder(h);logit=out[:,:,2]+6*has-2
        positive=1+(base+.05)*torch.exp(2*torch.tanh(out[:,:,0]/2))+F.softplus(out[:,:,1])
        return torch.sigmoid(logit)*positive+1e-6,logit,positive


def conditional_loss(mu,logit,positive,y,north,coefficient):
    active=y>0
    local=(positive[active]-y[active]*torch.log(positive[active])).mean() if active.any() else positive.sum()*0
    bce=F.binary_cross_entropy_with_logits(logit,active.float())
    total=F.smooth_l1_loss(mu.sum(1),y.sum(1),beta=100)/1000
    regional=0.
    for region in (north,~north):
        if region.any():regional=regional+F.smooth_l1_loss(mu[:,region].sum(1),y[:,region].sum(1),beta=100)/1000
    return coefficient*local+.2*bce+total+.25*regional
