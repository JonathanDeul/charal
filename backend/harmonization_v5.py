"""Full-month neural count models with optional spatial/temporal attention."""
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
import torch
from torch import nn
from torch.nn import functional as F
from backend.harmonization_v2 import SeasonalRatio,NUMERIC
from backend.harmonization_v4 import features,RICH


class MonthData:
    def __init__(self,root):
        self.root=Path(root)
        frame=pd.read_csv(self.root/'data/research/harmonization_v4/cells.csv.gz',dtype={'ecoregion':str})
        self.cells=frame[['gy','gx','latitude','longitude']].drop_duplicates().sort_values(['gy','gx']).reset_index(drop=True)
        self.dates=sorted(frame.date.unique());self.C=len(self.cells)
        frame=frame.sort_values(['date','gy','gx']).reset_index(drop=True);self.frame=frame
        self.X=features(frame).astype(np.float32).reshape(len(self.dates),self.C,-1)
        self.y=frame.viirs_count.to_numpy(np.float32).reshape(len(self.dates),self.C)
        self.count=frame.modis_count.to_numpy(np.float32).reshape(len(self.dates),self.C)
        self.complete=frame.pair_complete.to_numpy().reshape(len(self.dates),self.C).all(axis=1)&np.isfinite(self.y).all(axis=1)
        self.years=np.array([int(x[:4]) for x in self.dates]);self.months=np.array([int(x[5:7]) for x in self.dates])
        self.north=self.cells.latitude.to_numpy()>=39.5
        original=len(NUMERIC)+4
        self.fine=list(range(original))+[original+i for i,c in enumerate(RICH) if not c.startswith(('neighbor','previous'))]
        a=np.load(self.root/'data/research/harmonization_v3/daily.npz');dates=pd.DatetimeIndex(a['date'])
        # Daily source cube order is verified by its separate stored grid.
        grid=pd.read_csv(self.root/'data/research/harmonization_v3/grid.csv')[['gy','gx']]
        mapping={(r.gy,r.gx):i for i,r in grid.iterrows()}
        order=[mapping[(r.gy,r.gx)] for r in self.cells.itertuples()]
        self.temporal=np.zeros((len(self.dates),self.C,8,20),np.float32)
        for i,date in enumerate(self.dates):
            selected=(dates.strftime('%Y-%m')==date[:7]);daily=a['local'][selected][:,order,:]
            if not len(daily):continue
            padded=np.zeros((32,self.C,5),np.float32)
            padded[:len(daily),:,:4]=np.log1p(daily)/np.array([3,3,6,3],np.float32)
            padded[:len(daily),:,4]=1
            self.temporal[i]=padded.transpose(1,0,2).reshape(self.C,8,20)

    def indices(self,years):return np.flatnonzero((self.years>=years[0])&(self.years<=years[1])&self.complete)

    def fit_inputs(self,idx,feature_set):
        cols=self.fine if feature_set=='fine' else list(range(self.X.shape[2]))
        scaler=StandardScaler().fit(self.X[idx][:,:,cols].reshape(-1,len(cols)))
        f=self.frame[self.frame.date.isin([self.dates[i] for i in idx])]
        ratio=SeasonalRatio().fit(f)
        ratios=np.array([ratio.ratios[m] for m in range(1,13)],np.float32)
        return {'columns':cols,'mean':scaler.mean_.astype(np.float32),'scale':scaler.scale_.astype(np.float32),'ratios':ratios}

    def tensors(self,inputs,device):
        x=np.clip((self.X[:,:,inputs['columns']]-inputs['mean'])/inputs['scale'],-8,8)
        base=self.count*inputs['ratios'][self.months-1,None]
        # No target fills are ever included in input tensors.
        return {k:torch.from_numpy(v).to(device) for k,v in {
            'x':x.astype(np.float32),'base':base,'has':(self.count>0).astype(np.float32),
            'temporal':self.temporal,'y':np.nan_to_num(self.y,nan=0)}.items()}

    def evaluated_frame(self,idx):
        dates={self.dates[i] for i in idx};return self.frame[self.frame.date.isin(dates)].copy()


class NeuralHurdle(nn.Module):
    def __init__(self,n_features,architecture):
        super().__init__();self.architecture=architecture
        if architecture=='mlp':
            self.encoder=nn.Sequential(nn.Linear(n_features,64),nn.SiLU(),nn.Dropout(.1),nn.Linear(64,64),nn.SiLU(),nn.Dropout(.1),nn.Linear(64,32),nn.SiLU())
        elif architecture=='spatial':
            self.project=nn.Linear(n_features,32)
            layer=nn.TransformerEncoderLayer(d_model=32,nhead=4,dim_feedforward=64,dropout=.1,batch_first=True,norm_first=True,activation='gelu')
            self.encoder=nn.TransformerEncoder(layer,num_layers=2,enable_nested_tensor=False)
        else:
            self.temporal_project=nn.Linear(20,32);self.position=nn.Parameter(torch.randn(1,8,32)*.02)
            layer=nn.TransformerEncoderLayer(d_model=32,nhead=4,dim_feedforward=64,dropout=.1,batch_first=True,norm_first=True,activation='gelu')
            self.temporal_encoder=nn.TransformerEncoder(layer,num_layers=2,enable_nested_tensor=False)
            self.encoder=nn.Sequential(nn.Linear(n_features+32,64),nn.SiLU(),nn.Dropout(.1),nn.Linear(64,32),nn.SiLU())
        self.head=nn.Linear(32,3);nn.init.zeros_(self.head.weight);self.head.bias.data[:]=torch.tensor([0.,-3.,0.])

    def forward(self,x,base,has,temporal):
        if self.architecture=='spatial':h=self.encoder(self.project(x))
        elif self.architecture=='temporal':
            b,c=base.shape
            seq=self.temporal_project(temporal.reshape(b*c,8,20))+self.position
            htime=self.temporal_encoder(seq).mean(dim=1).reshape(b,c,32)
            h=self.encoder(torch.cat([x,htime],dim=-1))
        else:h=self.encoder(x)
        out=self.head(h);logit=out[:,:,2]+6*has-2
        positive=1+base*torch.exp(2*torch.tanh(out[:,:,0]/2))+F.softplus(out[:,:,1])
        return torch.sigmoid(logit)*positive+1e-6,logit


def joint_loss(mu,logit,y,north,local_weight):
    local=(mu-y*torch.log(mu)).mean()
    presence=F.binary_cross_entropy_with_logits(logit,(y>0).float())
    total=F.smooth_l1_loss(mu.sum(1),y.sum(1),beta=100)/1000
    regional=0.
    for region in (north,~north):
        if region.any():regional=regional+F.smooth_l1_loss(mu[:,region].sum(1),y[:,region].sum(1),beta=100)/1000
    return local_weight*local+.05*presence+total+.25*regional
