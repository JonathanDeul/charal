#!/usr/bin/env python3
"""Execute the frozen daily context experiment and preserve all research fits."""
from __future__ import annotations
import os
os.environ.setdefault('OMP_NUM_THREADS','4')
os.environ.setdefault('OPENBLAS_NUM_THREADS','4')
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import pickle
import sys
import time
import numpy as np
import pandas as pd
import torch
from sklearn.ensemble import HistGradientBoostingRegressor

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend.harmonization_v3 import DailyData,CountNet,metrics
OUT=ROOT/'data/research/harmonization_v3';MODELS=ROOT/'models/harmonization_v3'
PROTOCOL=ROOT/'research/harmonization_v3/protocol.json'


def save(path,obj):
    temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(obj,indent=2,allow_nan=False));temporary.replace(path)


def features(data,idx,years,ratios,context):
    arrays=[]
    for start in range(0,len(idx),4096):
        patch,meta,_=data.batch(idx[start:start+4096],years,ratios,context)
        arrays.append(np.concatenate([patch.reshape(len(patch),-1),meta],axis=1))
    return np.concatenate(arrays).astype(np.float32)


def predict_net(model,data,idx,years,ratios):
    model.eval();values=[]
    with torch.no_grad():
        for start in range(0,len(idx),4096):
            patch,meta,base=data.batch(idx[start:start+4096],years,ratios,model.context)
            values.append(model(torch.from_numpy(patch),torch.from_numpy(meta),torch.from_numpy(base)).numpy())
    return np.concatenate(values)


def fit_net(name,seed,data,idx,years,ratios,epochs,audit=None,stage='development'):
    torch.manual_seed(seed);rng=np.random.default_rng(seed)
    context=name!='mlp_poisson';model=CountNet(data.static.shape[1]+2,context,name=='cnn_nb')
    model.train();optimizer=torch.optim.AdamW(model.parameters(),lr=.001,weight_decay=.001)
    selected,weight=data.sample(idx,42) # identical sample across all models/seeds
    normalization=weight.sum()/len(weight)
    history=[];predictions={}
    for epoch in range(1,epochs+1):
        t0=time.monotonic();order=rng.permutation(len(selected));total=0.
        model.train()
        for start in range(0,len(order),2048):
            positions=order[start:start+2048];batch=selected[positions]
            patch,meta,base=data.batch(batch,years,ratios,context)
            y=torch.from_numpy(data.target.ravel()[batch]);w=torch.from_numpy(weight[positions]/normalization)
            mu=model(torch.from_numpy(patch),torch.from_numpy(meta),torch.from_numpy(base))
            loss=(model.loss(mu,y)*w).mean()
            if not torch.isfinite(loss):raise ValueError('Nonfinite neural loss')
            optimizer.zero_grad();loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),10.);optimizer.step()
            total+=float(loss.detach())*len(batch)/len(selected)
        if name=='cnn_poisson_aggregate':
            times=idx//data.C;months=data.dates.strftime('%Y-%m').to_numpy()[times]
            unique=np.unique(months)
            for month in rng.permutation(unique):
                batch=idx[months==month];patch,meta,base=data.batch(batch,years,ratios,context)
                mu=model(torch.from_numpy(patch),torch.from_numpy(meta),torch.from_numpy(base))
                y=torch.from_numpy(data.target.ravel()[batch]);north=data.grid.latitude.to_numpy()[batch%data.C]>=39.5
                loss=0.
                for region in (north,~north):
                    if region.any():loss=loss+.05*(torch.log1p(mu[region].sum())-torch.log1p(y[region].sum()))**2
                optimizer.zero_grad();loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),10.);optimizer.step()
        record={'epoch':epoch,'loss':total,'seconds':time.monotonic()-t0}
        if model.nb:record['alpha']=float(torch.nn.functional.softplus(model.raw_alpha).detach()+.001)
        history.append(record)
        print(stage,name,seed,'epoch',epoch,'loss',round(total,3),'seconds',round(record['seconds'],1),flush=True)
        if audit is not None and epoch in (2,4,8):
            ai,ay=audit;predictions[epoch]=predict_net(model,data,ai,ay,ratios)
            np.savez_compressed(OUT/f'dev_{name}_{seed}_epoch{epoch}.npz',prediction=predictions[epoch])
        torch.save({'state_dict':model.state_dict(),'context':context,'nb':model.nb,'nmeta':data.static.shape[1]+2,
                    'ratios':ratios.tolist(),'years':years,'seed':seed,'epoch':epoch},MODELS/f'{stage}_{name}_{seed}.pt')
    return model,history,predictions


def predict_boost(model,data,idx,years,ratios,context):
    values=[]
    for start in range(0,len(idx),4096):
        chunk=idx[start:start+4096];patch,meta,base=data.batch(chunk,years,ratios,context)
        x=np.concatenate([patch.reshape(len(chunk),-1),meta],axis=1)
        values.append((base+.05)*model.predict(x))
    return np.concatenate(values)


def fit_boost(data,idx,years,ratios,context):
    selected,w=data.sample(idx,42);x=features(data,selected,years,ratios,context)
    t=selected//data.C;c=selected%data.C;base=data.count[t,c]*ratios[data.dates.month.to_numpy()[t]-1]+.05
    model=HistGradientBoostingRegressor(loss='poisson',max_iter=100,learning_rate=.05,max_leaf_nodes=15,
        min_samples_leaf=100,l2_regularization=10,early_stopping=False,random_state=42)
    model.fit(x,data.target.ravel()[selected]/base,sample_weight=w*base)
    return model


def run():
    torch.set_num_threads(4);torch.set_num_interop_threads(1)
    start=time.monotonic();MODELS.mkdir(parents=True,exist_ok=True)
    protocol=json.loads(PROTOCOL.read_text());data=DailyData(ROOT)
    report={'protocol':protocol,'protocol_sha256':hashlib.sha256(PROTOCOL.read_bytes()).hexdigest(),
        'environment':{p:version(p) for p in ['torch','numpy','pandas','scipy','scikit-learn','shapely']},
        'manifest':json.loads((OUT/'manifest.json').read_text()),'development':{},'selection':{},'known_benchmark':{},'backward_audit':{}}
    devtrain,devguard=data.indices(protocol['development_train'],[protocol['development_validate'],protocol['selection'],protocol['known_benchmark']])
    dev,devinfo=data.indices(protocol['development_validate']);devframe=data.frame(dev)
    train,guard=data.indices(protocol['final_train'],[protocol['selection'],protocol['known_benchmark']])
    valid,validinfo=data.indices(protocol['selection']);vframe=data.frame(valid);vframe['large_event']=data.event_strata(valid)
    ratios_dev=data.ratios(devtrain);ratios=data.ratios(train)
    report['training']={'development':devguard,'final':guard,'development_validation':devinfo,'selection':validinfo,
        'development_sample_rows':len(data.sample(devtrain)[0]),'final_sample_rows':len(data.sample(train)[0]),
        'calfire_linked_groups':len(data.events),'final_ratios':ratios.tolist()}
    save(OUT/'run_setup.json',report)
    # Development chooses neural epochs only. No 2021+ predictions here.
    selected_epochs={}
    histories={}
    for name in protocol['models']:
        if name in ('seasonal_ratio','boost_point','boost_context'):continue
        ensemble={e:[] for e in protocol['neural_epoch_candidates']};histories[name]={}
        for seed in protocol['seeds']:
            model,hist,pred=fit_net(name,seed,data,devtrain,protocol['development_train'],ratios_dev,8,(dev,protocol['development_validate']))
            histories[name][str(seed)]=hist
            for e,p in pred.items():ensemble[e].append(p)
        scores={str(e):metrics(devframe,np.mean(values,axis=0)) for e,values in ensemble.items()}
        report['development'][name]=scores
        selected_epochs[name]=min(protocol['neural_epoch_candidates'],key=lambda e:scores[str(e)]['monthly_mae'])
        report['selected_epochs']=selected_epochs
        save(OUT/'development.json',report);save(OUT/'histories.json',histories)
        print('Development selected',name,selected_epochs[name],flush=True)
    fitted={};vpred={};seed_metrics={};final_histories={}
    for name in protocol['models']:
        if name=='seasonal_ratio':
            base=data.batch(valid,protocol['selection'],ratios,False)[2];vpred[name]=base;fitted[name]=None
        elif name.startswith('boost'):
            context=name=='boost_context';model=fit_boost(data,train,protocol['final_train'],ratios,context);fitted[name]=model
            with (MODELS/f'{name}.pkl').open('wb') as f:pickle.dump({'model':model,'ratios':ratios,'context':context},f)
            vpred[name]=predict_boost(model,data,valid,protocol['selection'],ratios,context)
        else:
            models=[];pred=[];seed_metrics[name]={};final_histories[name]={}
            for seed in protocol['seeds']:
                model,hist,_=fit_net(name,seed,data,train,protocol['final_train'],ratios,selected_epochs[name],stage='final')
                models.append(model);p=predict_net(model,data,valid,protocol['selection'],ratios);pred.append(p)
                seed_metrics[name][str(seed)]=metrics(vframe,p);final_histories[name][str(seed)]=hist
            fitted[name]=models;vpred[name]=np.mean(pred,axis=0)
        report['selection'][name]=metrics(vframe,vpred[name])
        print('Selection',name,round(report['selection'][name]['monthly_mae'],2),flush=True)
        save(OUT/'selection_progress.json',report)
    report['selected_candidate']=min(protocol['models'],key=lambda n:report['selection'][n]['monthly_mae'])
    report['selection_seed_metrics']=seed_metrics
    report['production_changed']=False
    save(OUT/'selection.json',report) # Seal before benchmark/backward predictions.
    save(OUT/'final_histories.json',final_histories)
    frames={'selection':(valid,vframe,protocol['selection'])}
    for split,years in [('known_benchmark',protocol['known_benchmark']),('backward_audit',protocol['backward_audit'])]:
        idx,info=data.indices(years);frame=data.frame(idx);frame['large_event']=data.event_strata(idx);frames[split]=(idx,frame,years)
    for split,(idx,frame,years) in frames.items():
        export=frame.copy();export['flat_index']=idx
        for name in protocol['models']:
            if split=='selection':prediction=vpred[name]
            elif name=='seasonal_ratio':prediction=data.batch(idx,years,ratios,False)[2]
            elif name.startswith('boost'):prediction=predict_boost(fitted[name],data,idx,years,ratios,name=='boost_context')
            else:
                preds=[predict_net(m,data,idx,years,ratios) for m in fitted[name]];prediction=np.mean(preds,axis=0)
                report.setdefault('audit_seed_metrics',{}).setdefault(split,{})[name]={str(seed):metrics(frame,p) for seed,p in zip(protocol['seeds'],preds)}
            if not np.isfinite(prediction).all() or (prediction<0).any():raise ValueError('Invalid count predictions')
            export[name]=prediction;report[split][name]=metrics(frame,prediction)
            print(split,name,round(report[split][name]['monthly_mae'],2),flush=True)
        export.to_csv(OUT/f'{split}_predictions.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    report['elapsed_seconds']=time.monotonic()-start
    report['source_sha256']={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in ['backend/harmonization_v3.py','scripts/prepare_harmonization_v3.py','scripts/train_harmonization_v3.py']}
    save(OUT/'report.json',report)
    print('Complete:',report['selected_candidate'],'elapsed minutes',round(report['elapsed_seconds']/60,1),flush=True)


if __name__=='__main__':run()
