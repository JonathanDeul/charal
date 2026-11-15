"""Daily context experiment helpers. Offline research only."""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
from shapely.geometry import shape, box
from shapely.strtree import STRtree
import torch
from torch import nn
from torch.nn import functional as F


def event_groups(records, grid):
    parent=list(range(len(records))); owners={}
    def find(i):
        while parent[i]!=i:parent[i]=parent[parent[i]];i=parent[i]
        return i
    for i,r in enumerate(records):
        for field in ['irwin_id','complex_id']:
            key=str(r.get(field) or '').strip().strip('{}').lower()
            if not key:continue
            if key in owners:parent[find(i)]=find(owners[key])
            else:owners[key]=i
    groups={}
    cells=[box(r.gx/2,r.gy/2,(r.gx+1)/2,(r.gy+1)/2) for r in grid.itertuples()]
    tree=STRtree(cells)
    for i,r in enumerate(records):
        g=groups.setdefault(find(i),{'ids':[],'start':pd.Timestamp.max,'end':pd.Timestamp.min,'cells':set(),'area_ha':0.,'missing_dates':False})
        start=pd.to_datetime(r.get('alarm_date_ms'),unit='ms',errors='coerce')
        end=pd.to_datetime(r.get('containment_date_ms'),unit='ms',errors='coerce')
        if pd.isna(start):start=pd.Timestamp(int(r['year']),1,1);g['missing_dates']=True
        if pd.isna(end) or end<start:end=max(start,pd.Timestamp(int(r['year']),12,31));g['missing_dates']=True
        g['start']=min(g['start'],start.normalize());g['end']=max(g['end'],end.normalize())
        g['area_ha']=max(g['area_ha'],float(r.get('area_ha',0))) # no double-counted parent/child area sum
        g['ids'].append(r['id'])
        if r.get('geometry'):g['cells'].update(tree.query(shape(r['geometry']).buffer(0),predicate='intersects').tolist())
    return list(groups.values())


class DailyData:
    def __init__(self,root):
        self.root=Path(root);p=self.root/'data/research/harmonization_v3'
        a=np.load(p/'daily.npz');self.a={k:a[k] for k in a.files};self.dates=pd.DatetimeIndex(a['date'])
        self.grid=pd.read_csv(p/'grid.csv',dtype={'ecoregion':str});self.C=len(self.grid)
        self.count=a['local'][:,:,:2].sum(axis=2);self.target=a['target']
        self.events=event_groups(json.loads((self.root/'data/processed/perimeters.json').read_text()),self.grid)
        self.ecos=sorted(self.grid.ecoregion.unique());eco=np.eye(len(self.ecos),dtype=np.float32)[[self.ecos.index(x) for x in self.grid.ecoregion]]
        self.static=np.column_stack([(self.grid.latitude-37)/5,(self.grid.longitude+120)/5,eco]).astype(np.float32)
        # log transforms are fixed, not learned using held-out observations.
        self.logged=np.log1p(a['context']).astype(np.float32)/np.array([3,3,6,3],np.float32)
        self.logged_local=np.log1p(a['local']).astype(np.float32)/np.array([3,3,6,3],np.float32)

    def indices(self,years,purge_against=None):
        days=(self.dates.year>=years[0])&(self.dates.year<=years[1])&self.a['pair_complete']
        mask=np.broadcast_to(days[:,None],self.target.shape).copy();removed=0;crossing=[]
        if purge_against:
            train_start=pd.Timestamp(years[0],1,1);train_end=pd.Timestamp(years[1],12,31)
            for g in self.events:
                gs,ge=g['start']-pd.Timedelta(days=3),g['end']+pd.Timedelta(days=3)
                if ge<train_start or gs>train_end:continue
                if not any(gs<=pd.Timestamp(b,12,31) and ge>=pd.Timestamp(a,1,1) for a,b in purge_against):continue
                if not g['cells']:continue
                # Remove any training patch whose spatial/temporal support
                # could intersect this known cross-boundary event group.
                loc=self.grid[['gy','gx']].to_numpy();e=loc[sorted(g['cells'])]
                nearby=np.max(np.abs(loc[:,None,:]-e[None,:,:]),axis=2).min(axis=1)<=2
                td=(self.dates>=gs)&(self.dates<=ge)
                before=int(mask.sum());mask[np.ix_(td,nearby)]=False;removed+=before-int(mask.sum())
                crossing.append({'ids':g['ids'],'start':str(g['start'].date()),'end':str(g['end'].date()),'missing_dates':g['missing_dates']})
        idx=np.flatnonzero(mask.ravel())
        return idx,{'years':years,'rows':len(idx),'purged_rows':removed,'crossing_groups':crossing}

    def sample(self,idx,seed=42):
        rng=np.random.default_rng(seed)
        active=(self.count.ravel()[idx]>0)|(self.target.ravel()[idx]>0)
        keep=active|(rng.random(len(idx))<.1)
        selected=idx[keep];w=np.where(active[keep],1.,10.).astype(np.float32)
        return selected,w

    def ratios(self,idx):
        t=idx//self.C;m=self.dates.month.to_numpy()[t];x=self.count.ravel()[idx];y=self.target.ravel()[idx]
        global_ratio=y.sum()/max(x.sum(),1)
        return np.array([y[m==k].sum()/x[m==k].sum() if x[m==k].sum() else global_ratio for k in range(1,13)],np.float32)

    def batch(self,idx,years,ratios,context=True):
        t=idx//self.C;c=idx%self.C;n=len(idx)
        months=self.dates.month.to_numpy()[t]
        meta=np.column_stack([self.static[c],np.sin(months*2*np.pi/12),np.cos(months*2*np.pi/12)]).astype(np.float32)
        base=self.count[t,c]*ratios[months-1]
        if not context:
            patch=np.concatenate([self.logged_local[t,c],np.ones((n,1),np.float32)],axis=1)
            return patch,meta,base
        shifts=np.arange(-3,4);sp=np.arange(-2,3)
        tt=t[:,None]+shifts[None,:];clipped=np.clip(tt,0,len(self.dates)-1)
        valid=(tt>=0)&(tt<len(self.dates))&self.a['context_day_valid'][clipped]
        yy=self.dates.year.to_numpy()[clipped];valid&=(yy>=years[0])&(yy<=years[1])
        y=self.a['grid_y'][c,None,None]+sp[None,:,None]
        x=self.a['grid_x'][c,None,None]+sp[None,None,:]
        patch=self.logged[clipped[:,:,None,None],y[:,None,:,:],x[:,None,:,:],:].copy()
        # Match exactly the local state-clipped information used by point models.
        patch[:,:,2,2,:]=self.logged_local[clipped,c[:,None],:]
        spatial=self.a['support'][y,x]
        availability=valid[:,:,None,None]&spatial[:,None,:,:]
        patch*=availability[:,:,:,:,None]
        patch=np.concatenate([patch,availability[:,:,:,:,None].astype(np.float32)],axis=4)
        patch=patch.transpose(0,1,4,2,3).reshape(n,35,5,5)
        return patch,meta,base

    def frame(self,idx):
        t=idx//self.C;c=idx%self.C
        return pd.DataFrame({'date':self.dates[t].strftime('%Y-%m-%d'),'month':self.dates[t].strftime('%Y-%m'),
            'cell':c,'gy':self.grid.gy.to_numpy()[c],'gx':self.grid.gx.to_numpy()[c],
            'latitude':self.grid.latitude.to_numpy()[c],'modis_count':self.count[t,c],'viirs_count':self.target[t,c]})

    def event_strata(self,idx):
        mask=np.zeros(self.target.shape,bool)
        for g in self.events:
            if g['area_ha']<10000 or not g['cells']:continue
            days=(self.dates>=g['start'])&(self.dates<=g['end'])
            mask[np.ix_(days,sorted(g['cells']))]=True
        return mask.ravel()[idx]


class CountNet(nn.Module):
    def __init__(self,nmeta,context=True,nb=False):
        super().__init__();self.context=context;self.nb=nb
        if context:
            self.encoder=nn.Sequential(nn.Conv2d(35,8,3),nn.SiLU(),nn.Flatten())
            width=72
        else:self.encoder=nn.Identity();width=5
        self.head=nn.Sequential(nn.Linear(width+nmeta,24),nn.SiLU(),nn.Linear(24,2))
        nn.init.zeros_(self.head[-1].weight);self.head[-1].bias.data[:]=torch.tensor([0.,-3.])
        if nb:self.raw_alpha=nn.Parameter(torch.tensor(-1.))

    def forward(self,patch,meta,base):
        out=self.head(torch.cat([self.encoder(patch),meta],dim=1))
        return base*torch.exp(3*torch.tanh(out[:,0]/3))+F.softplus(out[:,1])+1e-6

    def loss(self,mu,y):
        if not self.nb:return mu-y*torch.log(mu)
        alpha=F.softplus(self.raw_alpha)+.001;r=1/alpha
        return (y+r)*torch.log1p(mu/r)-y*torch.log(mu)+y*torch.log(r)-torch.lgamma(y+r)+torch.lgamma(r)+torch.lgamma(y+1)


def metrics(frame,pred):
    f=frame.copy();f['prediction']=pred;f['error']=pred-f.viirs_count
    def calc(a):
        if not len(a):return None
        monthly=a.groupby('month')[['viirs_count','prediction']].sum();e=monthly.prediction-monthly.viirs_count
        return {'n':len(a),'months':len(monthly),'cell_daily_mae':float(a.error.abs().mean()),'monthly_mae':float(e.abs().mean()),
            'monthly_wape':float(e.abs().sum()/max(monthly.viirs_count.sum(),1)),'bias_total':float(a.error.sum()),
            'reference_total':float(a.viirs_count.sum()),'predicted_total':float(a.prediction.sum())}
    result=calc(f);result['north']=calc(f[f.latitude>=39.5]);result['south']=calc(f[f.latitude<39.5])
    result['zero_modis_daily']=calc(f[f.modis_count==0]);result['zero_modis_viirs_positive_daily']=calc(f[(f.modis_count==0)&(f.viirs_count>0)])
    cm=f.groupby(['month','cell']).agg(modis_count=('modis_count','sum'),viirs_count=('viirs_count','sum'),prediction=('prediction','sum'))
    cm['error']=cm.prediction-cm.viirs_count
    def cm_score(a):
        return {'n':len(a),'mae':float(a.error.abs().mean()),'bias_total':float(a.error.sum()),
            'reference_total':float(a.viirs_count.sum()),'predicted_total':float(a.prediction.sum())} if len(a) else None
    result['cell_month']=cm_score(cm);result['zero_modis_month']=cm_score(cm[cm.modis_count==0]);result['high_activity_month']=cm_score(cm[cm.modis_count>=500])
    if 'large_event' in f:result['large_event_daily']=calc(f[f.large_event])
    result['monthly']=f.groupby('month')[['viirs_count','prediction']].sum().reset_index().to_dict('records')
    return result
