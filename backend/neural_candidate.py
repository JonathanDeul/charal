"""Portable inference for the frozen v7 pointwise neural ensemble.

Input is the already-derived MODIS feature table from prepare_harmonization_v4,
not raw satellite imagery. VIIRS/year columns, if supplied, are ignored.
"""
from pathlib import Path
import numpy as np
import torch
from backend.harmonization_v4 import features
from backend.harmonization_v7 import EmbeddedHurdle


class NeuralCandidate:
    def __init__(self,root,device='cpu'):
        self.device=torch.device(device);self.members=[]
        if device=='mps' and not torch.backends.mps.is_available():raise RuntimeError('Requested MPS unavailable')
        root=Path(root)
        for seed in [42,43,44]:
            path=root/f'models/harmonization_v7/final_plr_mlp_conditional_{seed}.pt'
            checkpoint=torch.load(path,map_location='cpu',weights_only=True)
            if checkpoint['config']['architecture']!='plr_mlp':raise ValueError('Unexpected candidate architecture')
            inputs={k:np.array(v,np.float32) if k!='columns' else v for k,v in checkpoint['inputs'].items()}
            net=EmbeddedHurdle(len(inputs['columns']),'plr_mlp',checkpoint['state_dict']['knots'])
            net.load_state_dict(checkpoint['state_dict']);net.to(self.device).eval();self.members.append((net,inputs))

    def predict(self,frame,batch_size=4096):
        raw=features(frame).astype(np.float32)
        month=frame.month.to_numpy().astype(int)
        if not ((month>=1)&(month<=12)).all():raise ValueError('Calendar month outside1..12')
        count=frame.modis_count.to_numpy(np.float32);values=[]
        if (count<0).any() or not np.isfinite(raw).all():raise ValueError('Invalid MODIS inputs')
        with torch.no_grad():
            for start in range(0,len(frame),batch_size):
                stop=min(start+batch_size,len(frame));members=[]
                has=torch.from_numpy((count[start:stop]>0).astype(np.float32)[None,:]).to(self.device)
                for net,inputs in self.members:
                    x=np.clip((raw[start:stop,inputs['columns']]-inputs['mean'])/inputs['scale'],-8,8)
                    base=count[start:stop]*inputs['ratios'][month[start:stop]-1]
                    mu,_,_=net(torch.from_numpy(x[None,:,:]).to(self.device),torch.from_numpy(base[None,:]).to(self.device),has,None)
                    members.append(mu.cpu().numpy().ravel())
                values.append(np.mean(members,axis=0))
        return np.concatenate(values) if values else np.empty(0,np.float32)
