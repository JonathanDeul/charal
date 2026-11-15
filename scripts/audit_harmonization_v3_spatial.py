#!/usr/bin/env python3
"""Refit frozen families on spatially buffered training cells for a transfer audit."""
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
import torch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend.harmonization_v3 import DailyData,metrics
from scripts.train_harmonization_v3 import fit_net,fit_boost,predict_net,predict_boost,save
OUT=ROOT/'data/research/harmonization_v3'


def main():
    torch.set_num_threads(4);torch.set_num_interop_threads(1)
    report=json.loads((OUT/'report.json').read_text());data=DailyData(ROOT)
    train,guard=data.indices([2013,2020],[[2021,2022],[2023,2025]])
    audit,_=data.indices([2023,2025]);north=data.grid.latitude.to_numpy()>=39.5
    audit=audit[north[audit%data.C]]
    coords=data.grid[['latitude','longitude']].to_numpy()
    separation=np.max(np.abs(coords[:,None,:]-coords[north][None,:,:]),axis=2).min(axis=1)
    train=train[separation[train%data.C]>2]
    ratios=data.ratios(train);frame=data.frame(audit);frame['large_event']=data.event_strata(audit)
    output={'protocol':json.loads((ROOT/'research/harmonization_v3/spatial_audit_protocol.json').read_text()),
        'train_rows':len(train),'train_cells':len(np.unique(train%data.C)),'evaluation_rows':len(audit),
        'minimum_center_separation_degrees':float(separation[np.unique(train%data.C)].min()),'metrics':{},'seed_metrics':{}}
    export=frame.copy();export['flat_index']=audit
    for name in report['protocol']['models']:
        if name=='seasonal_ratio':pred=data.batch(audit,[2023,2025],ratios,False)[2]
        elif name.startswith('boost'):
            context=name=='boost_context';model=fit_boost(data,train,[2013,2020],ratios,context)
            pred=predict_boost(model,data,audit,[2023,2025],ratios,context)
        else:
            predictions=[];output['seed_metrics'][name]={}
            for seed in report['protocol']['seeds']:
                model,hist,_=fit_net(name,seed,data,train,[2013,2020],ratios,report['selected_epochs'][name],stage='spatial')
                p=predict_net(model,data,audit,[2023,2025],ratios);predictions.append(p)
                output['seed_metrics'][name][str(seed)]=metrics(frame,p)
            pred=np.mean(predictions,axis=0)
        output['metrics'][name]=metrics(frame,pred);export[name]=pred
        print('Spatial audit',name,round(output['metrics'][name]['monthly_mae'],2),flush=True)
        save(OUT/'spatial_audit.json',output)
    export.to_csv(OUT/'spatial_predictions.csv.gz',index=False,compression={'method':'gzip','mtime':0})


if __name__=='__main__':main()
