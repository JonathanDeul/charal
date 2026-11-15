"""Separate Terra/Aqua descriptors and small modality-fusion neural models."""
import json
import numpy as np
import pandas as pd
import torch
from torch import nn
from torch.nn import functional as F
from backend.harmonization_v5 import MonthData


class PlatformMonthData(MonthData):
    def __init__(self,root):
        super().__init__(root)
        extra=pd.read_csv(self.root/'data/research/harmonization_platforms/cells.csv.gz',dtype={'ecoregion':str}).sort_values(['date','gy','gx']).reset_index(drop=True)
        np.testing.assert_array_equal(extra[['date','gy','gx']].to_numpy(),self.frame[['date','gy','gx']].to_numpy())
        manifest=json.loads((self.root/'data/research/harmonization_platforms/manifest.json').read_text())
        aqua=[c for c in manifest['features'] if c.startswith('aqua_')];terra=[c for c in manifest['features'] if c.startswith('terra_')]
        self.n_fine=len(self.fine);self.n_platform=len(aqua)
        source=extra[aqua+terra].to_numpy(np.float32)
        source=np.sign(source)*np.log1p(np.abs(source))
        fine=self.X[:,:,self.fine]
        self.X=np.concatenate([fine,source.reshape(len(self.dates),self.C,-1)],axis=2)
        self.fine=list(range(self.X.shape[2]));self.frame=extra
        self.platform_count=extra[['aqua_n','terra_n']].to_numpy(np.float32).reshape(len(self.dates),self.C,2)

    def fit_inputs(self,idx,feature_set='fine'):
        inputs=super().fit_inputs(idx,feature_set)
        f=self.frame[self.frame.date.isin([self.dates[i] for i in idx])]
        ratios=[]
        for source in ['aqua_n','terra_n']:
            g=f.groupby('month')[['viirs_count',source]].sum()
            fallback=f.viirs_count.sum()/max(f[source].sum(),1)
            ratios.append([g.loc[m,'viirs_count']/g.loc[m,source] if g.loc[m,source]>0 else fallback for m in range(1,13)])
        inputs['platform_ratios']=np.array(ratios,np.float32).T
        return inputs

    def tensors(self,inputs,device):
        tensors=super().tensors(inputs,device)
        base=self.platform_count*inputs['platform_ratios'][self.months-1,None,:]
        tensors['base']=torch.from_numpy(base).to(device)
        return tensors


class PlatformFusionNet(nn.Module):
    def __init__(self,n_fine,n_platform,architecture):
        super().__init__();self.n_fine=n_fine;self.n_platform=n_platform;self.architecture=architecture
        if architecture=='platform_transformer':
            self.project=nn.Linear(n_fine+n_platform,32);self.platform_id=nn.Parameter(torch.randn(1,2,32)*.02)
            self.cls=nn.Parameter(torch.zeros(1,1,32))
            layer=nn.TransformerEncoderLayer(32,4,dim_feedforward=64,dropout=.1,batch_first=True,norm_first=True,activation='gelu')
            self.encoder=nn.TransformerEncoder(layer,2,enable_nested_tensor=False);width=32
        else:
            self.encoder=nn.Sequential(nn.Linear(n_fine+2*n_platform,64),nn.ReLU(),nn.Dropout(.1),nn.Linear(64,64),nn.ReLU());width=64
        self.head=nn.Linear(width,6);nn.init.zeros_(self.head.weight);self.head.bias.data[:]=torch.tensor([0.,0.,0.,0.,-3.,0.])

    def forward(self,x,base,has,temporal):
        if self.architecture=='platform_transformer':
            b,c,f=x.shape;fine=x[:,:,:self.n_fine];p=x[:,:,self.n_fine:].reshape(b,c,2,self.n_platform)
            tokens=self.project(torch.cat([fine[:,:,None,:].expand(-1,-1,2,-1),p],dim=-1)).reshape(b*c,2,32)+self.platform_id
            tokens=torch.cat([self.cls.expand(b*c,-1,-1),tokens],dim=1)
            h=self.encoder(tokens)[:,0].reshape(b,c,32)
        else:h=self.encoder(x)
        out=self.head(h);correction=torch.exp(2*torch.tanh(out[:,:,:2]/2));gates=torch.softmax(out[:,:,2:4],dim=-1)
        positive=1+(base*correction*gates).sum(-1)+F.softplus(out[:,:,4]);logit=out[:,:,5]+6*has-2
        return torch.sigmoid(logit)*positive+1e-6,logit,positive
