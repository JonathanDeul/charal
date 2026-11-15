#!/usr/bin/env python3
"""Frozen numeric embedding/feature-Transformer comparison on MPS."""
import os
os.environ.setdefault('OMP_NUM_THREADS','4')
from pathlib import Path
import hashlib,json,sys,time
import numpy as np
import torch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend.harmonization_v5 import MonthData
from backend.harmonization_v7 import EmbeddedHurdle,conditional_loss
from scripts.train_harmonization_v2 import diagnostics
OUT=ROOT/'data/research/harmonization_v7';MDIR=ROOT/'models/harmonization_v7';PROTOCOL=ROOT/'research/harmonization_v7/protocol.json'


def save(name,obj):
    p=OUT/name;t=p.with_suffix('.tmp');t.write_text(json.dumps(obj,indent=2,allow_nan=False));t.replace(p)


def predict(model,t,idx):
    model.eval();values=[]
    with torch.no_grad():
        for i in range(0,len(idx),8):
            ids=idx[i:i+8];mu,_,_=model(t['x'][ids],t['base'][ids],t['has'][ids],t['temporal'][ids]);values.append(mu.cpu().numpy())
    return np.concatenate(values).reshape(-1)


def fit(config,seed,data,inputs,idx,epochs,stage,valid=None):
    torch.manual_seed(seed);rng=np.random.default_rng(seed);t=data.tensors(inputs,'mps')
    x=t['x'][idx].cpu().numpy().reshape(-1,len(inputs['columns']))
    knots=torch.from_numpy(np.quantile(x,np.linspace(0,1,9),axis=0).T.astype(np.float32))
    net=EmbeddedHurdle(len(inputs['columns']),config['architecture'],knots).to('mps');north=torch.from_numpy(data.north).to('mps')
    opt=torch.optim.AdamW(net.parameters(),lr=.001,weight_decay=.01);scheduler=torch.optim.lr_scheduler.CosineAnnealingLR(opt,T_max=320,eta_min=.0001)
    preds={};hist=[]
    for epoch in range(1,epochs+1):
        start=time.monotonic();net.train();order=rng.permutation(idx);total=0.
        for i in range(0,len(order),8):
            ids=order[i:i+8];mu,logit,pos=net(t['x'][ids],t['base'][ids],t['has'][ids],t['temporal'][ids])
            loss=conditional_loss(mu,logit,pos,t['y'][ids],north,config['local_weight'])
            if not torch.isfinite(loss):raise ValueError('Nonfinite loss')
            opt.zero_grad();loss.backward();torch.nn.utils.clip_grad_norm_(net.parameters(),5.);opt.step();total+=float(loss.detach().cpu())*len(ids)/len(order)
        scheduler.step();torch.mps.synchronize();hist.append({'epoch':epoch,'loss':total,'seconds':time.monotonic()-start})
        if epoch%20==0:print(stage,config['name'],seed,'epoch',epoch,'loss',round(total,3),'seconds',round(hist[-1]['seconds'],2),flush=True)
        if valid is not None and epoch in [20,40,80,160,320]:preds[epoch]=predict(net,t,valid)
    torch.save({'state_dict':{k:v.detach().cpu() for k,v in net.state_dict().items()},'config':config,'inputs':{k:v.tolist() if hasattr(v,'tolist') else v for k,v in inputs.items()},'epoch':epochs,'seed':seed},MDIR/f'{stage}_{config["name"]}_{seed}.pt')
    return net,t,hist,preds


def run():
    if not torch.backends.mps.is_available():raise RuntimeError('MPS required')
    torch.set_num_threads(4);torch.backends.mha.set_fastpath_enabled(False)
    OUT.mkdir(parents=True,exist_ok=True);MDIR.mkdir(parents=True,exist_ok=True)
    p=json.loads(PROTOCOL.read_text());data=MonthData(ROOT);start=time.monotonic()
    report={'protocol':p,'protocol_sha256':hashlib.sha256(PROTOCOL.read_bytes()).hexdigest(),'device':'mps','development':{},'selection':{},'known_benchmark':{},'backward_audit':{}}
    td=data.indices(p['development_training']);vd=data.indices(p['development_validation']);df=data.evaluated_frame(vd)
    train=data.indices(p['training']);valid=data.indices(p['selection']);vf=data.evaluated_frame(valid)
    epochs={}
    for cfg in p['configs']:
        name=cfg['name'];path=OUT/f'development_{name}.json'
        if path.exists():
            obj=json.loads(path.read_text());report['development'][name]=obj['scores'];epochs[name]=obj['epoch'];continue
        inputs=data.fit_inputs(td,'fine');ensemble={e:[] for e in p['epoch_candidates']};history={}
        for seed in p['seeds']:
            net,t,hist,preds=fit(cfg,seed,data,inputs,td,320,'development',vd);history[str(seed)]=hist
            for e,pred in preds.items():ensemble[e].append(pred)
            del net,t
        scores={str(e):diagnostics(df,np.mean(preds,axis=0)) for e,preds in ensemble.items()}
        epochs[name]=min(p['epoch_candidates'],key=lambda e:scores[str(e)]['monthly_mae']);report['development'][name]=scores
        save(f'development_{name}.json',{'scores':scores,'epoch':epochs[name],'history':history});print('Chosen',name,epochs[name],scores[str(epochs[name])]['monthly_mae'],flush=True)
    report['selected_epochs']=epochs;save('development.json',report);fitted={};seed_scores={};histories={}
    for cfg in p['configs']:
        name=cfg['name'];inputs=data.fit_inputs(train,'fine');models=[];preds=[];seed_scores[name]={};histories[name]={}
        for seed in p['seeds']:
            net,t,hist,_=fit(cfg,seed,data,inputs,train,epochs[name],'final');pred=predict(net,t,valid)
            models.append(net);preds.append(pred);seed_scores[name][str(seed)]=diagnostics(vf,pred);histories[name][str(seed)]=hist
        report['selection'][name]=diagnostics(vf,np.mean(preds,axis=0));fitted[name]=(models,t);save('selection_progress.json',report)
        print('SELECTION',name,report['selection'][name]['monthly_mae'],flush=True)
    winner=min(report['selection'],key=lambda n:report['selection'][n]['monthly_mae']);report['selected_candidate']=winner;report['seed_scores']=seed_scores
    report['threshold_met']=report['selection'][winner]['monthly_mae']<500;save('selection.json',report);save('final_histories.json',histories)
    nets,t=fitted[winner]
    for label,years in [('selection',p['selection']),('known_benchmark',p['known_benchmark']),('backward_audit',p['backward_audit'])]:
        idx=data.indices(years);frame=data.evaluated_frame(idx);pred=np.mean([predict(net,t,idx) for net in nets],axis=0)
        report[label][winner]=diagnostics(frame,pred);export=frame[['date','gy','gx','modis_count','viirs_count']].copy();export['candidate']=pred
        export.to_csv(OUT/f'{label}_predictions.csv.gz',index=False,compression={'method':'gzip','mtime':0});print(label,winner,report[label][winner]['monthly_mae'],flush=True)
    report['elapsed_seconds']=time.monotonic()-start;report['production_changed']=False
    report['source_sha256']={path:hashlib.sha256((ROOT/path).read_bytes()).hexdigest() for path in ['backend/harmonization_v5.py','backend/harmonization_v7.py','scripts/train_harmonization_v7.py']}
    save('report.json',report);print('Done threshold',report['threshold_met'],flush=True)


if __name__=='__main__':run()
