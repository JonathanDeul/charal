#!/usr/bin/env python3
"""Train and audit the fixed hierarchical neural follow-up on MPS."""
import os
os.environ.setdefault('OMP_NUM_THREADS','4')
from pathlib import Path
import hashlib,json,sys,time
import numpy as np
import torch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend.harmonization_v5 import MonthData,joint_loss
from backend.harmonization_v6 import RegionalCountNet
from scripts.train_harmonization_v2 import diagnostics
from scripts.train_harmonization_v5 import predict
OUT=ROOT/'data/research/harmonization_v6';MDIR=ROOT/'models/harmonization_v6';PROTOCOL=ROOT/'research/harmonization_v6/protocol.json'


def save(name,obj):
    p=OUT/name;t=p.with_suffix('.tmp');t.write_text(json.dumps(obj,indent=2,allow_nan=False));t.replace(p)


def fit(config,seed,data,inputs,train,epochs,stage,valid=None):
    torch.manual_seed(seed);rng=np.random.default_rng(seed);device=torch.device('mps');t=data.tensors(inputs,device)
    north=torch.from_numpy(data.north).to(device)
    model=RegionalCountNet(len(inputs['columns']),config['architecture'],north).to(device)
    opt=torch.optim.AdamW(model.parameters(),lr=.001,weight_decay=.03)
    schedule=torch.optim.lr_scheduler.CosineAnnealingLR(opt,T_max=320,eta_min=.0001)
    history=[];preds={}
    for epoch in range(1,epochs+1):
        start=time.monotonic();model.train();order=rng.permutation(train);total=0.
        for i in range(0,len(order),8):
            ids=order[i:i+8];mu,logit=model(t['x'][ids],t['base'][ids],t['has'][ids],t['temporal'][ids])
            loss=joint_loss(mu,logit,t['y'][ids],north,config['local_weight'])
            if not torch.isfinite(loss):raise ValueError('Nonfinite loss')
            opt.zero_grad();loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),5.);opt.step()
            total+=float(loss.detach().cpu())*len(ids)/len(order)
        schedule.step();torch.mps.synchronize();history.append({'epoch':epoch,'loss':total,'seconds':time.monotonic()-start})
        if epoch%40==0:print(stage,config['name'],seed,'epoch',epoch,'loss',round(total,3),flush=True)
        if valid is not None and epoch in [40,80,160,320]:
            preds[epoch]=predict(model,t,valid)
    torch.save({'state_dict':{k:v.detach().cpu() for k,v in model.state_dict().items()},'config':config,
        'inputs':{k:v.tolist() if hasattr(v,'tolist') else v for k,v in inputs.items()},'epoch':epochs,'seed':seed},MDIR/f'{stage}_{config["name"]}_{seed}.pt')
    return model,t,history,preds


def run():
    if not torch.backends.mps.is_available():raise RuntimeError('MPS required')
    torch.set_num_threads(4);OUT.mkdir(parents=True,exist_ok=True);MDIR.mkdir(parents=True,exist_ok=True)
    p=json.loads(PROTOCOL.read_text());data=MonthData(ROOT);start=time.monotonic()
    report={'protocol':p,'protocol_sha256':hashlib.sha256(PROTOCOL.read_bytes()).hexdigest(),'device':'mps','development':{},'selection':{},'known_benchmark':{},'backward_audit':{}}
    train_dev=data.indices(p['development_training']);dev=data.indices(p['development_validation']);df=data.evaluated_frame(dev)
    train=data.indices(p['training']);valid=data.indices(p['selection']);vf=data.evaluated_frame(valid)
    selected_epochs={}
    for cfg in p['configs']:
        name=cfg['name'];cache=OUT/f'development_{name}.json'
        if cache.exists():
            obj=json.loads(cache.read_text());report['development'][name]=obj['scores'];selected_epochs[name]=obj['epoch'];continue
        inputs=data.fit_inputs(train_dev,'fine');ensembles={e:[] for e in p['epoch_candidates']};hist={}
        for seed in p['seeds']:
            model,t,history,preds=fit(cfg,seed,data,inputs,train_dev,320,'development',dev);hist[str(seed)]=history
            for e,pred in preds.items():ensembles[e].append(pred)
            del model,t
        scores={str(e):diagnostics(df,np.mean(values,axis=0)) for e,values in ensembles.items()}
        selected_epochs[name]=min(p['epoch_candidates'],key=lambda e:scores[str(e)]['monthly_mae']);report['development'][name]=scores
        save(f'development_{name}.json',{'scores':scores,'epoch':selected_epochs[name],'history':hist})
        print('Chosen epoch',name,selected_epochs[name],'dev',scores[str(selected_epochs[name])]['monthly_mae'],flush=True)
    report['selected_epochs']=selected_epochs;save('development.json',report)
    fitted={};seeds={};histories={}
    for cfg in p['configs']:
        name=cfg['name'];inputs=data.fit_inputs(train,'fine');models=[];preds=[];seeds[name]={};histories[name]={}
        for seed in p['seeds']:
            model,t,hist,_=fit(cfg,seed,data,inputs,train,selected_epochs[name],'final');pred=predict(model,t,valid)
            models.append(model);preds.append(pred);seeds[name][str(seed)]=diagnostics(vf,pred);histories[name][str(seed)]=hist
        report['selection'][name]=diagnostics(vf,np.mean(preds,axis=0));fitted[name]=(models,t)
        print('SELECTION',name,report['selection'][name]['monthly_mae'],flush=True);save('selection_progress.json',report)
    winner=min(report['selection'],key=lambda n:report['selection'][n]['monthly_mae']);report['selected_candidate']=winner
    report['threshold_met']=report['selection'][winner]['monthly_mae']<500;report['seed_scores']=seeds
    save('selection.json',report);save('final_histories.json',histories)
    models,t=fitted[winner]
    for label,years in [('selection',p['selection']),('known_benchmark',p['known_benchmark']),('backward_audit',p['backward_audit'])]:
        idx=data.indices(years);f=data.evaluated_frame(idx);pred=np.mean([predict(m,t,idx) for m in models],axis=0)
        report[label][winner]=diagnostics(f,pred)
        export=f[['date','gy','gx','modis_count','viirs_count']].copy();export['candidate']=pred;export.to_csv(OUT/f'{label}_predictions.csv.gz',index=False,compression={'method':'gzip','mtime':0})
        print(label,winner,report[label][winner]['monthly_mae'],flush=True)
    report['elapsed_seconds']=time.monotonic()-start;report['production_changed']=False
    report['source_sha256']={path:hashlib.sha256((ROOT/path).read_bytes()).hexdigest() for path in ['backend/harmonization_v5.py','backend/harmonization_v6.py','scripts/train_harmonization_v6.py']}
    save('report.json',report);print('Done threshold',report['threshold_met'],flush=True)


if __name__=='__main__':run()
