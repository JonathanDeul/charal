#!/usr/bin/env python3
"""Train full-month pure neural models on MPS; freeze before known benchmark."""
import os
os.environ.setdefault('OMP_NUM_THREADS','4');os.environ.setdefault('OPENBLAS_NUM_THREADS','4')
from pathlib import Path
import argparse
import hashlib
import json
import sys
import time
from importlib.metadata import version
import numpy as np
import torch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend.harmonization_v5 import MonthData,NeuralHurdle,joint_loss
from scripts.train_harmonization_v2 import diagnostics
OUT=ROOT/'data/research/harmonization_v5';MODELS=ROOT/'models/harmonization_v5'
PROTOCOL=ROOT/'research/harmonization_v5/protocol.json'


def save(name,obj):
    p=OUT/name;t=p.with_suffix('.tmp');t.write_text(json.dumps(obj,indent=2,allow_nan=False));t.replace(p)


def predict(model,tensors,indices):
    model.eval();values=[]
    with torch.no_grad():
        for start in range(0,len(indices),8):
            ids=indices[start:start+8]
            mu,_=model(tensors['x'][ids],tensors['base'][ids],tensors['has'][ids],tensors['temporal'][ids])
            values.append(mu.detach().cpu().numpy())
    return np.concatenate(values).reshape(-1)


def fit(config,seed,data,inputs,train_idx,epochs,device,stage,audit_idx=None):
    torch.manual_seed(seed);rng=np.random.default_rng(seed)
    tensors=data.tensors(inputs,device)
    model=NeuralHurdle(len(inputs['columns']),config['architecture']).to(device)
    optimizer=torch.optim.AdamW(model.parameters(),lr=.002,weight_decay=.01)
    scheduler=torch.optim.lr_scheduler.CosineAnnealingLR(optimizer,T_max=160,eta_min=.0002)
    north=torch.from_numpy(data.north).to(device)
    history=[];predictions={}
    for epoch in range(1,epochs+1):
        start=time.monotonic();model.train();order=rng.permutation(train_idx);total=0.
        for i in range(0,len(order),8):
            ids=order[i:i+8]
            mu,logit=model(tensors['x'][ids],tensors['base'][ids],tensors['has'][ids],tensors['temporal'][ids])
            loss=joint_loss(mu,logit,tensors['y'][ids],north,config['local_weight'])
            if not torch.isfinite(loss):raise ValueError('Nonfinite loss')
            optimizer.zero_grad();loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),5.);optimizer.step()
            total+=float(loss.detach().cpu())*len(ids)/len(order)
        scheduler.step()
        if device.type=='mps':torch.mps.synchronize()
        history.append({'epoch':epoch,'loss':total,'seconds':time.monotonic()-start})
        if epoch%20==0:
            print(stage,config['name'],seed,'epoch',epoch,'loss',round(total,3),'epoch seconds',round(history[-1]['seconds'],2),flush=True)
        if audit_idx is not None and epoch in [20,40,80,160]:
            pred=predict(model,tensors,audit_idx);predictions[epoch]=pred
            np.savez_compressed(OUT/f'dev_{config["name"]}_{seed}_epoch{epoch}.npz',prediction=pred)
    state={k:v.detach().cpu() for k,v in model.state_dict().items()}
    torch.save({'state_dict':state,'config':config,'inputs':{k:v.tolist() if hasattr(v,'tolist') else v for k,v in inputs.items()},'seed':seed,'epoch':epochs},
        MODELS/f'{stage}_{config["name"]}_{seed}.pt')
    return model,tensors,history,predictions


def run():
    parser=argparse.ArgumentParser();parser.add_argument('--device',choices=['mps','cpu'],default='mps');parser.add_argument('--only',default='');args=parser.parse_args()
    torch.set_num_threads(4);torch.backends.mha.set_fastpath_enabled(False)
    if args.device=='mps' and not torch.backends.mps.is_available():raise RuntimeError('Requested MPS unavailable; no silent CPU fallback')
    device=torch.device(args.device);OUT.mkdir(parents=True,exist_ok=True);MODELS.mkdir(parents=True,exist_ok=True)
    protocol=json.loads(PROTOCOL.read_text());data=MonthData(ROOT)
    report={'protocol':protocol,'protocol_sha256':hashlib.sha256(PROTOCOL.read_bytes()).hexdigest(),'device':str(device),
        'environment':{p:version(p) for p in ['torch','numpy','pandas','scikit-learn']},'development':{},'selection':{},'known_benchmark':{},'backward_audit':{}}
    configs=[c for c in protocol['configs'] if not args.only or c['name'] in args.only.split(',')]
    devtrain=data.indices(protocol['development_training']);dev=data.indices(protocol['development_validation'])
    train=data.indices(protocol['training']);valid=data.indices(protocol['selection'])
    dframe=data.evaluated_frame(dev);vframe=data.evaluated_frame(valid)
    chosen_epochs={};histories={};start=time.monotonic()
    for config in configs:
        name=config['name'];path=OUT/f'development_{name}.json'
        if path.exists():
            cached=json.loads(path.read_text());report['development'][name]=cached['scores'];chosen_epochs[name]=cached['chosen_epoch']
            print('Resume completed development',name,flush=True);continue
        inputs=data.fit_inputs(devtrain,config['features']);ensemble={e:[] for e in protocol['epoch_candidates']};histories[name]={}
        for seed in protocol['seeds']:
            model,tensors,hist,pred=fit(config,seed,data,inputs,devtrain,160,device,'development',dev)
            histories[name][str(seed)]=hist
            for epoch,p in pred.items():ensemble[epoch].append(p)
            del model,tensors
        scores={str(e):diagnostics(dframe,np.mean(p,axis=0)) for e,p in ensemble.items()}
        chosen_epochs[name]=min(protocol['epoch_candidates'],key=lambda e:scores[str(e)]['monthly_mae'])
        report['development'][name]=scores
        save(f'development_{name}.json',{'chosen_epoch':chosen_epochs[name],'scores':scores,'history':histories[name]})
        print('Epoch choice',name,chosen_epochs[name],'development MAE',scores[str(chosen_epochs[name])]['monthly_mae'],flush=True)
    report['chosen_epochs']=chosen_epochs;save('development.json',report)
    fitted={};final_hist={};seed_scores={}
    for config in configs:
        name=config['name'];inputs=data.fit_inputs(train,config['features']);models=[];preds=[];final_hist[name]={};seed_scores[name]={}
        for seed in protocol['seeds']:
            model,tensors,hist,_=fit(config,seed,data,inputs,train,chosen_epochs[name],device,'final')
            p=predict(model,tensors,valid);models.append(model);preds.append(p)
            seed_scores[name][str(seed)]=diagnostics(vframe,p);final_hist[name][str(seed)]=hist
        report['selection'][name]=diagnostics(vframe,np.mean(preds,axis=0));fitted[name]=(models,tensors)
        print('SELECTION',name,report['selection'][name]['monthly_mae'],flush=True)
        save('selection_progress.json',report)
    report['selected_candidate']=min(report['selection'],key=lambda n:report['selection'][n]['monthly_mae'])
    report['threshold_met']=report['selection'][report['selected_candidate']]['monthly_mae']<500
    report['seed_scores']=seed_scores;save('selection.json',report);save('final_histories.json',final_hist)
    # Only the selected family is audited after the selection checkpoint.
    winner=report['selected_candidate'];models,tensors=fitted[winner]
    for label,years in [('selection',protocol['selection']),('known_benchmark',protocol['known_benchmark']),('backward_audit',protocol['backward_audit'])]:
        idx=data.indices(years);f=data.evaluated_frame(idx);preds=[predict(m,tensors,idx) for m in models];pred=np.mean(preds,axis=0)
        report[label][winner]=diagnostics(f,pred)
        f=f[['date','gy','gx','modis_count','viirs_count']].copy();f['candidate']=pred
        f.to_csv(OUT/f'{label}_predictions.csv.gz',index=False,compression={'method':'gzip','mtime':0})
        print(label,winner,report[label][winner]['monthly_mae'],flush=True)
    report['elapsed_seconds']=time.monotonic()-start;report['production_changed']=False
    report['source_sha256']={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in ['backend/harmonization_v5.py','scripts/train_harmonization_v5.py']}
    save('report.json',report);print('Complete; threshold met:',report['threshold_met'],flush=True)


if __name__=='__main__':run()
