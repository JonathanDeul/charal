"""Neural regional-total pooling and count-conserving cell allocation."""
import math
import torch
from torch import nn
from torch.nn import functional as F


class RegionalCountNet(nn.Module):
    def __init__(self,n_features,architecture,north):
        super().__init__();self.architecture=architecture
        self.register_buffer('regions',torch.stack([north,~north]).float(),persistent=False)
        self.encoder=nn.Sequential(nn.Linear(n_features,32),nn.SiLU(),nn.Dropout(.15),nn.Linear(32,32),nn.SiLU())
        if architecture.startswith('attention'):
            self.key=nn.Linear(32,32);self.value=nn.Linear(32,32);self.query=nn.Parameter(torch.randn(2,2,16)*.02)
            self.pool_norm=nn.LayerNorm(32)
        self.region_head=nn.Sequential(nn.Linear(32+n_features+4,16),nn.SiLU(),nn.Dropout(.15),nn.Linear(16,2))
        nn.init.zeros_(self.region_head[-1].weight);self.region_head[-1].bias.data[:]=torch.tensor([0.,-3.])
        self.local_head=nn.Linear(32,3);nn.init.zeros_(self.local_head.weight);self.local_head.bias.data[:]=torch.tensor([0.,-3.,0.])

    def forward(self,x,base,has,temporal):
        h=self.encoder(x);b,c=base.shape;mask=self.regions[None,:,:]
        region_base=(base[:,None,:]*mask).sum(-1)
        fixed=(base[:,None,:]+.1)*mask;fixed=fixed/(fixed.sum(-1,keepdim=True)+1e-6)
        raw_pool=torch.matmul(fixed,x)
        if self.architecture.startswith('attention'):
            key=self.key(h).reshape(b,c,2,16).permute(0,2,1,3)
            score=(key[:,None,:,:,:]*self.query[None,:,:,None,:]).sum(-1)/math.sqrt(16)
            score=score+torch.log(base+.1)[:,None,None,:]
            score=score.masked_fill(mask[:,:,None,:]==0,-1e4)
            attention=torch.softmax(score,dim=-1)*mask[:,:,None,:]
            attention=attention/(attention.sum(-1,keepdim=True)+1e-6)
            value=self.value(h).reshape(b,c,2,16).permute(0,2,1,3)
            pool=torch.matmul(attention.unsqueeze(-2),value[:,None,:,:,:]).squeeze(-2).reshape(b,2,32)
            pool=self.pool_norm(pool)
        else:pool=torch.matmul(fixed,h)
        denominator=mask.sum(-1).clamp_min(1)
        active=(has[:,None,:]*mask).sum(-1)/denominator
        concentration=(base[:,None,:].square()*mask).sum(-1)/(region_base.square()+1)
        largest=(base[:,None,:]*mask).amax(-1)/(region_base+1)
        summary=torch.stack([torch.log1p(region_base)/10,active,concentration,largest],dim=-1)
        raw=self.region_head(torch.cat([pool,raw_pool,summary],dim=-1))
        total=region_base*torch.exp(.7*torch.tanh(raw[:,:,0]/.7))+F.softplus(raw[:,:,1])
        local=self.local_head(h);logit=local[:,:,2]+6*has-2
        if self.architecture.endswith('fixed'):local_weight=base
        else:local_weight=base*torch.exp(.3*torch.tanh(local[:,:,0]/.3))+torch.sigmoid(logit)*F.softplus(local[:,:,1])
        shares=local_weight[:,None,:]*mask
        shares=shares/(shares.sum(-1,keepdim=True)+1e-6)
        mu=(total[:,:,None]*shares).sum(1)+1e-6
        return mu,logit
