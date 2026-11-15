#!/usr/bin/env python3
"""Train a larger contextual Transformer. Never changes the active calendar."""
import os
os.environ.setdefault('OMP_NUM_THREADS','4')
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import sys
import time
import numpy as np
import torch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend.harmonization_v9 import ContextData,SpaceTimeTransformer,count_loss
from scripts.train_harmonization_v2 import diagnostics


def save_json(path,value):
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(value,indent=2,allow_nan=False));temp.replace(path)


def predict(net,data,indices,device,batch_size):
    net.eval();values=[]
    with torch.no_grad():
        for index in indices:
            for start in range(0,data.C,batch_size):
                cells=np.arange(start,min(start+batch_size,data.C))
                values.extend(net(data.batch(index,cells,device))[0].cpu().tolist())
    return np.asarray(values)


def train(args,data,train_idx,valid_idx,epochs,stage,out,device):
    random.seed(args.seed);np.random.seed(args.seed);torch.manual_seed(args.seed)
    data.fit(train_idx)
    config={'n_static':data.X.shape[1],'width':args.width,'heads':args.heads,
            'temporal_layers':args.temporal_layers,'spatial_layers':args.spatial_layers,'dropout':args.dropout}
    net=SpaceTimeTransformer(**config).to(device)
    optimizer=torch.optim.AdamW(net.parameters(),lr=args.lr,weight_decay=.01)
    scheduler=torch.optim.lr_scheduler.CosineAnnealingLR(optimizer,T_max=args.epochs,eta_min=args.lr*.05)
    best=float('inf');best_epoch=0;history=[];started=time.monotonic()
    for epoch in range(1,epochs+1):
        net.train();loss_total=0.;n=0
        for index in np.random.permutation(train_idx):
            cells=np.random.permutation(data.C)
            for start in range(0,data.C,args.batch_size):
                batch=data.batch(index,cells[start:start+args.batch_size],device)
                prediction,logit,positive=net(batch)
                loss=count_loss(prediction,logit,positive,batch['target'])
                if not torch.isfinite(loss):raise RuntimeError('Nonfinite training loss')
                optimizer.zero_grad(set_to_none=True);loss.backward()
                torch.nn.utils.clip_grad_norm_(net.parameters(),1.);optimizer.step()
                loss_total+=float(loss.detach().cpu())*len(batch['target']);n+=len(batch['target'])
        scheduler.step()
        record={'epoch':epoch,'loss':loss_total/n,'elapsed_seconds':time.monotonic()-started}
        improved=False
        if valid_idx is not None and (epoch%args.eval_every==0 or epoch==epochs):
            p=predict(net,data,valid_idx,device,args.batch_size)
            score=diagnostics(data.rows(valid_idx),p)
            record['validation']=score
            if score['monthly_mae']<best:
                best=score['monthly_mae'];best_epoch=epoch;improved=True
        elif valid_idx is None:best_epoch=epoch;improved=True
        history.append(record)
        checkpoint={'state_dict':{k:v.detach().cpu() for k,v in net.state_dict().items()},
            'config':config,'preprocessing':data.preprocessing(),'epoch':epoch,'seed':args.seed,
            'training_years':sorted(data.rows(train_idx).year.unique().tolist()),'args':vars(args),
            'optimizer':optimizer.state_dict(),'scheduler':scheduler.state_dict()}
        # Atomic writes allow interruption without destroying the last checkpoint.
        temp=out/f'{stage}_last.tmp';torch.save(checkpoint,temp);temp.replace(out/f'{stage}_last.pt')
        if improved:
            temp=out/f'{stage}_best.tmp';torch.save(checkpoint,temp);temp.replace(out/f'{stage}_best.pt')
        save_json(out/f'{stage}_history.json',history)
        print(stage,epoch,'loss',round(record['loss'],4),'validation MAE',round(best,2) if valid_idx is not None else '-',flush=True)
        if valid_idx is not None and best_epoch and epoch-best_epoch>=args.patience:break
    return best_epoch


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--device',choices=['mps','cpu','cuda'],default='mps')
    p.add_argument('--width',type=int,default=128);p.add_argument('--heads',type=int,default=8)
    p.add_argument('--temporal-layers',type=int,default=3);p.add_argument('--spatial-layers',type=int,default=3)
    p.add_argument('--radius',type=int,default=2);p.add_argument('--halo',type=int,default=3)
    p.add_argument('--batch-size',type=int,default=16);p.add_argument('--epochs',type=int,default=600)
    p.add_argument('--patience',type=int,default=60);p.add_argument('--eval-every',type=int,default=5)
    p.add_argument('--dropout',type=float,default=.1);p.add_argument('--lr',type=float,default=.0003)
    p.add_argument('--seed',type=int,default=42)
    p.add_argument('--output',default='models/harmonization_v9/seed42')
    p.add_argument('--check-only',action='store_true',help='Validate real inputs and forward inference; no optimization or checkpoints')
    args=p.parse_args()
    for name in ['width','heads','temporal_layers','spatial_layers','batch_size','epochs','patience','eval_every']:
        if getattr(args,name)<1:p.error(f'{name} must be positive')
    if args.radius<0 or args.halo<0 or not 0<=args.dropout<1 or args.lr<=0:p.error('Invalid context/dropout/learning rate')
    if args.width%args.heads:p.error('width must be divisible by heads')
    if args.device=='mps' and not torch.backends.mps.is_available():raise RuntimeError('MPS unavailable; no silent CPU fallback')
    if args.device=='cuda' and not torch.cuda.is_available():raise RuntimeError('CUDA unavailable')
    torch.set_num_threads(4);torch.backends.mha.set_fastpath_enabled(False)
    data=ContextData(ROOT,args.radius,args.halo)
    td,vd=data.indices(2013,2018),data.indices(2019,2020)
    if not len(td) or not len(vd):raise RuntimeError('Training or development months missing')
    if args.check_only:
        data.fit(td);net=SpaceTimeTransformer(data.X.shape[1],args.width,args.temporal_layers,args.spatial_layers,args.heads,args.dropout).to(args.device).eval()
        with torch.no_grad():
            batch=data.batch(vd[0],np.arange(min(2,data.C)),args.device);value=net(batch)[0]
        assert torch.isfinite(value).all() and (value>=0).all()
        print(json.dumps({'check_only':True,'optimization_steps':0,'device':args.device,'parameters':sum(x.numel() for x in net.parameters()),'daily_shape':list(batch['daily'].shape),'static_features':data.X.shape[1],'prediction':value.cpu().tolist()}));return
    out=ROOT/args.output
    if out.exists() and any(out.iterdir()):raise FileExistsError('Choose an empty --output directory; existing results are never overwritten')
    out.mkdir(parents=True,exist_ok=True)
    paths=['backend/harmonization_v9.py','scripts/train_harmonization_v9.py','data/research/harmonization_v3/daily.npz','data/research/harmonization_v4/cells.csv.gz','research/harmonization_v9/protocol.json']
    save_json(out/'manifest.json',{'created':datetime.now(timezone.utc).isoformat(),'args':vars(args),'source_hashes':{s:hashlib.sha256((ROOT/s).read_bytes()).hexdigest() for s in paths}})
    best_epoch=train(args,data,td,vd,args.epochs,'development',out,args.device)
    # Seal duration before evaluating previously inspected external audit years.
    save_json(out/'selection.json',{'epoch':best_epoch,'rule':'Minimum 2019-2020 monthly MAE; no 2021+ labels used to select duration','production_changed':False})
    train(args,data,data.indices(2013,2020),None,best_epoch,'final',out,args.device)
    checkpoint=torch.load(out/'final_best.pt',map_location='cpu',weights_only=False)
    net=SpaceTimeTransformer(**checkpoint['config']).to(args.device);net.load_state_dict(checkpoint['state_dict'])
    report={'selected_epoch':best_epoch,'production_changed':False,'audits':{}}
    for label,years in [('selection',(2021,2022)),('known_benchmark',(2023,2025)),('backward',(2012,2012))]:
        indices=data.indices(*years);frame=data.rows(indices);pred=predict(net,data,indices,args.device,args.batch_size)
        report['audits'][label]={'candidate':diagnostics(frame,pred),'paired_ratio':diagnostics(frame,data.ratio.predict(frame))}
        if (ROOT/'models/harmonization_release/candidate.pkl').exists():
            import pickle
            with (ROOT/'models/harmonization_release/candidate.pkl').open('rb') as handle:
                active=pickle.load(handle)['model']
            report['audits'][label]['active_historical_transfer']=diagnostics(frame,active.predict(frame))
        export=frame[['date','gy','gx','viirs_count']].copy();export['prediction']=pred;export.to_csv(out/f'{label}_predictions.csv.gz',index=False)
    save_json(out/'report.json',report)
    print('Completed research model. Active harmonization unchanged.',flush=True)


if __name__=='__main__':main()
