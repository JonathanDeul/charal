"""Factorized daily-space Transformer; training-only MODIS climatology."""
from pathlib import Path
import numpy as np
import pandas as pd
import torch
from torch import nn
from backend.harmonization_v2 import SeasonalRatio
from backend.harmonization_v4 import features


def location_encoding(latitude, longitude):
    """Continuous absolute coordinates at several spatial wavelengths."""
    lat, lon = np.asarray(latitude), np.asarray(longitude)
    values = [lat / 90, lon / 180]
    for wavelength in [16., 8., 4., 2., 1.]:
        for coordinate in [lat, lon]:
            phase = coordinate * (2 * np.pi / wavelength)
            values.extend([np.sin(phase), np.cos(phase)])
    return np.stack(values, axis=-1).astype(np.float32)


class SeasonalReference:
    """No VIIRS inputs. Training examples use leave-own-year-out references."""
    def fit(self, frame):
        self.frame = frame[['year', 'month', 'gy', 'gx', 'modis_count', 'frp_sum']].copy()
        self.years = sorted(self.frame.year.unique().tolist())
        self.tables = {None: self._table(self.frame)}
        for year in self.years:
            self.tables[year] = self._table(self.frame[self.frame.year.ne(year)])
        return self

    @staticmethod
    def _table(frame):
        f = frame.copy()
        f['count'] = np.log1p(f.modis_count)
        f['frp'] = np.log1p(f.frp_sum)
        f['positive'] = (f.modis_count > 0).astype(float)
        g = f.groupby(['month', 'gy', 'gx']).agg(
            mean=('count', 'mean'), std=('count', 'std'), presence=('positive', 'mean'),
            frp=('frp', 'mean'), years=('year', 'nunique')).fillna(0)
        g['years'] = np.log1p(g.years)
        return g

    def transform(self, frame):
        out = np.zeros((len(frame), 5), np.float32)
        for year in frame.year.unique():
            mask = frame.year.to_numpy() == year
            # Applying to a fitted year always excludes that year, including
            # inference/checkpoint reproduction of training examples.
            table = self.tables.get(int(year), self.tables[None])
            keys = pd.MultiIndex.from_frame(frame.loc[mask, ['month', 'gy', 'gx']])
            out[mask] = table.reindex(keys).fillna(0).to_numpy(np.float32)
        return out


class ContextData:
    def __init__(self, root, radius=2, halo=3):
        root = Path(root)
        self.frame = pd.read_csv(root/'data/research/harmonization_v4/cells.csv.gz', dtype={'ecoregion': str}).sort_values(['date','gy','gx']).reset_index(drop=True)
        self.cells = self.frame[['gy','gx','latitude','longitude']].drop_duplicates().reset_index(drop=True)
        self.C = len(self.cells)
        self.dates = sorted(self.frame.date.unique())
        self.radius, self.halo = radius, halo
        a = np.load(root/'data/research/harmonization_v3/daily.npz')
        self.daily = a['context']; self.daily_dates = pd.DatetimeIndex(a['date'])
        self.support = a['support']; self.day_valid = a['context_day_valid']
        self.y0, self.x0 = int(a['gy0']), int(a['gx0'])
        self.offsets = np.array([(y,x) for y in range(-radius,radius+1) for x in range(-radius,radius+1)])
        self.X = features(self.frame).astype(np.float32)
        self.eligible = (self.frame.pair_complete.to_numpy().reshape(-1,self.C).all(1)
                         & self.frame.viirs_count.notna().to_numpy().reshape(-1,self.C).all(1))
        self._cache = {}

    def indices(self, start, end):
        years = np.array([int(d[:4]) for d in self.dates])
        return np.flatnonzero(self.eligible & (years>=start) & (years<=end))

    def rows(self, indices):
        return self.frame.iloc[np.concatenate([np.arange(i*self.C,(i+1)*self.C) for i in indices])].copy()

    def fit(self, indices):
        train = self.rows(indices)
        x = self.X[np.concatenate([np.arange(i*self.C,(i+1)*self.C) for i in indices])]
        self.mean, self.scale = x.mean(0), np.maximum(x.std(0), 1e-3)
        self.reference = SeasonalReference().fit(train)
        self.ratio = SeasonalRatio().fit(train)
        self.static = np.clip((self.X-self.mean)/self.scale,-8,8)
        self.normal = self.reference.transform(self.frame)
        self.base = self.ratio.predict(self.frame).astype(np.float32)
        return self

    def context(self, index):
        # Cache is bounded to keep unified memory available for attention.
        if index in self._cache: return self._cache[index]
        date = pd.Timestamp(self.dates[index]); end = date + pd.offsets.MonthEnd(0)
        days = pd.date_range(date-pd.Timedelta(days=self.halo),end+pd.Timedelta(days=self.halo))
        T = 31+2*self.halo; P = len(self.offsets)
        x = np.zeros((self.C,P,T,9),np.float32); valid = np.zeros((self.C,P,T),bool)
        location = np.zeros((self.C,P,26),np.float32)
        gy = self.cells.gy.to_numpy()[:,None]+self.offsets[None,:,0]
        gx = self.cells.gx.to_numpy()[:,None]+self.offsets[None,:,1]
        yy,xx = gy-self.y0,gx-self.x0
        inside=(yy>=0)&(yy<self.support.shape[0])&(xx>=0)&(xx<self.support.shape[1])
        yy=np.clip(yy,0,self.support.shape[0]-1);xx=np.clip(xx,0,self.support.shape[1]-1)
        supported=inside&self.support[yy,xx]
        location[:,:,:22]=location_encoding((gy+.5)/2,(gx+.5)/2)
        location[:,:,22]=self.offsets[None,:,0]*.25
        location[:,:,23]=self.offsets[None,:,1]*.25*np.cos(np.deg2rad(self.cells.latitude.to_numpy()))[:,None]
        location[:,:,24]=np.sqrt(location[:,:,22]**2+location[:,:,23]**2)
        location[:,:,25]=np.all(self.offsets==0,axis=1)[None]
        indices=self.daily_dates.get_indexer(days)
        for t,(day,j) in enumerate(zip(days,indices)):
            if j<0: continue
            good=supported&bool(self.day_valid[j]);valid[:,:,t]=good
            x[:,:,t,:4]=np.log1p(self.daily[j,yy,xx])/np.array([3,3,6,3])*good[:,:,None]
            phase=2*np.pi*(day.day_of_year-1)/365.25
            x[:,:,t,4:8]=[(day-date).days/31,np.sin(phase),np.cos(phase),float(day.month==date.month)]
            x[:,:,t,8]=good
        result = (x,valid,location)
        if len(self._cache)>=4: self._cache.pop(next(iter(self._cache)))
        self._cache[index] = result
        return result

    def batch(self,index,cells,device):
        x,valid,loc = self.context(index)
        row = index*self.C+np.asarray(cells)
        values = {'daily':x[cells],'valid':valid[cells],'location':loc[cells],
                  'static':self.static[row],'normal':self.normal[row], 'base':self.base[row],
                  'target':self.frame.viirs_count.to_numpy(np.float32)[row]}
        return {k:torch.as_tensor(v,device=device) for k,v in values.items()}

    def preprocessing(self):
        return {'mean':self.mean,'scale':self.scale,'reference':self.reference,'ratio':self.ratio,
                'radius':self.radius,'halo':self.halo,'cells':self.cells}


class SpaceTimeTransformer(nn.Module):
    def __init__(self, n_static, width=128, temporal_layers=3, spatial_layers=3, heads=8, dropout=.1):
        super().__init__()
        if width%heads: raise ValueError('width must be divisible by heads')
        self.daily_projection = nn.Linear(9,width)
        self.location_projection = nn.Linear(26,width)
        self.time_cls = nn.Parameter(torch.zeros(1,1,width))
        self.space_cls = nn.Parameter(torch.zeros(1,1,width))
        def encoder(layers):
            layer=nn.TransformerEncoderLayer(width,heads,width*4,dropout,activation='gelu',batch_first=True,norm_first=True)
            return nn.TransformerEncoder(layer,layers,enable_nested_tensor=False)
        self.temporal = encoder(temporal_layers)
        self.spatial = encoder(spatial_layers)
        self.static_projection = nn.Sequential(nn.Linear(n_static+5,width),nn.GELU(),nn.LayerNorm(width))
        self.head = nn.Sequential(nn.LayerNorm(2*width),nn.Linear(2*width,width),nn.GELU(),nn.Dropout(dropout),nn.Linear(width,3))
        nn.init.zeros_(self.head[-1].weight)
        self.head[-1].bias.data[:] = torch.tensor([0.,-2.,2.])

    def forward(self,batch):
        x,valid = batch['daily'],batch['valid']; B,P,T,_ = x.shape
        h=self.daily_projection(x).reshape(B*P,T,-1)
        h=torch.cat([self.time_cls.expand(B*P,-1,-1),h],1)
        mask=torch.cat([torch.zeros(B*P,1,dtype=torch.bool,device=x.device),~valid.reshape(B*P,T)],1)
        h=self.temporal(h,src_key_padding_mask=mask)[:,0].reshape(B,P,-1)
        h=h+self.location_projection(batch['location'])
        # The central query includes normal seasonal conditions and local state.
        query=self.space_cls.expand(B,-1,-1)+self.static_projection(torch.cat([batch['static'],batch['normal']],-1))[:,None]
        h=torch.cat([query,h],1)
        spatial_mask=torch.cat([torch.zeros(B,1,dtype=torch.bool,device=x.device),~valid.any(-1)],1)
        pooled=self.spatial(h,src_key_padding_mask=spatial_mask)[:,0]
        raw=self.head(torch.cat([pooled,query[:,0]],-1))
        probability=torch.sigmoid(raw[:,2])
        positive=1+(batch['base']+.05)*torch.exp(4*torch.tanh(raw[:,0]/4))+torch.nn.functional.softplus(raw[:,1])
        return probability*positive+1e-6,raw[:,2],positive


def count_loss(prediction, logit, positive, target):
    # Local conditional deviance plus presence and relative-count loss. No
    # aggregate accuracy claim is implied; monthly totals select checkpoints.
    active=target>0
    if active.any():
        y=target[active]; p=positive[active]
        deviance=((p-y+y*torch.log(y/p))/torch.sqrt(y+1)).mean()
    else: deviance=positive.sum()*0
    presence=torch.nn.functional.binary_cross_entropy_with_logits(logit,active.float())
    relative=torch.nn.functional.smooth_l1_loss(torch.log1p(prediction),torch.log1p(target))
    return .05*deviance+.2*presence+relative


def load_checkpoint(path, data, device='cpu'):
    """Restore trusted local research weights and their exact preprocessing."""
    checkpoint=torch.load(path,map_location='cpu',weights_only=False)
    state=checkpoint['preprocessing']
    if data.radius!=state['radius'] or data.halo!=state['halo']:
        raise ValueError('Context geometry differs from checkpoint')
    if not data.cells.equals(state['cells']):
        raise ValueError('Grid differs from checkpoint')
    data.mean,data.scale=state['mean'],state['scale']
    data.reference,data.ratio=state['reference'],state['ratio']
    data.static=np.clip((data.X-data.mean)/data.scale,-8,8)
    data.normal=data.reference.transform(data.frame)
    data.base=data.ratio.predict(data.frame).astype(np.float32)
    net=SpaceTimeTransformer(**checkpoint['config']).to(device)
    net.load_state_dict(checkpoint['state_dict']);net.eval()
    return net
