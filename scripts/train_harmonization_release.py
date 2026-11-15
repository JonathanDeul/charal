#!/usr/bin/env python3
"""Cross-fit experts and select conservative transfer weights without audit labels."""
import os
os.environ.setdefault('OMP_NUM_THREADS','4');os.environ.setdefault('OPENBLAS_NUM_THREADS','4')
from pathlib import Path
import hashlib,json,pickle,sys,time
import numpy as np
import pandas as pd
import torch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend.harmonization_v5 import MonthData
from backend.harmonization_v7 import EmbeddedHurdle,conditional_loss
from backend.harmonization_v2 import SeasonalRatio
from backend.harmonization_v4 import make_model
from scripts.train_harmonization_v2 import diagnostics,subset
from scripts.train_harmonization_v7 import predict
OUT=ROOT/'data/research/harmonization_release';MDIR=ROOT/'models/harmonization_release'
PROTOCOL=ROOT/'research/harmonization_release/protocol.json'


def save(name,obj):
    p=OUT/name;tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(obj,indent=2,allow_nan=False));tmp.replace(p)


def neural_fold(data,train_idx,test_idx,seed,name):
    torch.manual_seed(seed);rng=np.random.default_rng(seed);inputs=data.fit_inputs(train_idx,'fine');t=data.tensors(inputs,'mps')
    x=t['x'][train_idx].cpu().numpy().reshape(-1,len(inputs['columns']))
    knots=torch.from_numpy(np.quantile(x,np.linspace(0,1,9),axis=0).T.astype(np.float32))
    net=EmbeddedHurdle(len(inputs['columns']),'plr_mlp',knots).to('mps');north=torch.from_numpy(data.north).to('mps')
    opt=torch.optim.AdamW(net.parameters(),lr=.001,weight_decay=.01);schedule=torch.optim.lr_scheduler.CosineAnnealingLR(opt,T_max=320,eta_min=.0001)
    for epoch in range(160):
        net.train();order=rng.permutation(train_idx)
        for start in range(0,len(order),8):
            ids=order[start:start+8];mu,logit,pos=net(t['x'][ids],t['base'][ids],t['has'][ids],t['temporal'][ids])
            loss=conditional_loss(mu,logit,pos,t['y'][ids],north,.05)
            if not torch.isfinite(loss):raise ValueError('Nonfinite neural loss')
            opt.zero_grad();loss.backward();torch.nn.utils.clip_grad_norm_(net.parameters(),5);opt.step()
        schedule.step()
    torch.save({'state_dict':{k:v.detach().cpu() for k,v in net.state_dict().items()},'inputs':{k:v.tolist() if hasattr(v,'tolist') else v for k,v in inputs.items()},'epoch':160,'seed':seed},MDIR/f'{name}_seed{seed}.pt')
    return predict(net,t,test_idx)


def choose_weights(oof):
    choice={};all_options={}
    for region,mask in [('north',oof.latitude>=39.5),('south',oof.latitude<39.5)]:
        f=oof[mask];baseline_by_fold={name:diagnostics(block,block.seasonal_ratio.to_numpy()) for name,block in f.groupby('fold')}
        baseline_score=.7*np.mean([v['monthly_mae'] for n,v in baseline_by_fold.items() if n.startswith('backward')])+.3*np.mean([v['monthly_mae'] for n,v in baseline_by_fold.items() if n.startswith('forward')])
        options=[]
        for expert in ['v4_hurdle_rich','v7_embedding_mlp']:
            for weight in [.1,.25,.5,.75,1.]:
                fold_scores={};eligible=True
                for name,block in f.groupby('fold'):
                    prediction=(1-weight)*block.seasonal_ratio.to_numpy()+weight*block[expert].to_numpy()
                    score=diagnostics(block,prediction);b=baseline_by_fold[name]
                    eligible&=score['monthly_mae']<=1.05*b['monthly_mae'] and score['cell_month_mae']<=1.05*b['cell_month_mae']
                    fold_scores[name]=score
                score=.7*np.mean([v['monthly_mae'] for n,v in fold_scores.items() if n.startswith('backward')])+.3*np.mean([v['monthly_mae'] for n,v in fold_scores.items() if n.startswith('forward')])
                options.append({'expert':expert,'weight':weight,'score':score,'eligible':bool(eligible and score<=.95*baseline_score),'folds':fold_scores})
        acceptable=[x for x in options if x['eligible']]
        chosen=min(acceptable,key=lambda x:x['score']) if acceptable else {'expert':'seasonal_ratio','weight':0.,'score':baseline_score}
        choice[region]={k:v for k,v in chosen.items() if k!='folds'};all_options[region]={'baseline_score':baseline_score,'options':options}
    return choice,all_options


def run():
    if not torch.backends.mps.is_available():raise RuntimeError('MPS required')
    torch.set_num_threads(4);torch.backends.mha.set_fastpath_enabled(False)
    OUT.mkdir(exist_ok=True,parents=True);MDIR.mkdir(exist_ok=True,parents=True)
    protocol=json.loads(PROTOCOL.read_text());data=MonthData(ROOT);frame=data.frame
    pieces=[];start=time.monotonic()
    for fold in protocol['meta_folds']:
        path=OUT/f'{fold["name"]}.csv.gz'
        if path.exists():pieces.append(pd.read_csv(path));continue
        ti=data.indices(fold['train']);vi=data.indices(fold['predict']);tr=subset(frame,fold['train']);vf=data.evaluated_frame(vi)
        ratio=SeasonalRatio().fit(tr);tree=make_model('hurdle_rich').fit(tr)
        preds=[neural_fold(data,ti,vi,seed,fold['name']) for seed in [42,43,44]]
        f=vf[['date','year','month','gy','gx','latitude','longitude','modis_count','viirs_count']].copy()
        f['seasonal_ratio']=ratio.predict(vf);f['v4_hurdle_rich']=tree.predict(vf);f['v7_embedding_mlp']=np.mean(preds,axis=0);f['fold']=fold['name']
        f.to_csv(path,index=False,compression={'method':'gzip','mtime':0});pieces.append(f)
        print('OOF',fold['name'],{e:round(diagnostics(f,f[e].to_numpy())['monthly_mae'],2) for e in ['seasonal_ratio','v4_hurdle_rich','v7_embedding_mlp']},flush=True)
    oof=pd.concat(pieces,ignore_index=True);choice,options=choose_weights(oof)
    report={'protocol':protocol,'protocol_sha256':hashlib.sha256(PROTOCOL.read_bytes()).hexdigest(),'choice':choice,'options':options,'elapsed_seconds':time.monotonic()-start,'audit_years_used_for_selection':False}
    save('training_selection.json',report)
    print('Chosen conservative mixture',choice,flush=True)
    # Existing final experts were fitted on exactly the same 2013-2020 rows.
    from backend.neural_candidate import NeuralCandidate
    neural=NeuralCandidate(ROOT,device='mps');train=subset(frame,[2013,2020]);ratio=SeasonalRatio().fit(train)
    with (ROOT/'models/harmonization_v4/hurdle_rich.pkl').open('rb') as h:tree=pickle.load(h)
    report['audits']={}
    for label,years in protocol['audit_periods'].items():
        f=subset(frame,years);b=ratio.predict(f);t=tree.predict(f);n=neural.predict(f)
        p=b.copy()
        for region,mask in [('north',f.latitude.to_numpy()>=39.5),('south',f.latitude.to_numpy()<39.5)]:
            c=choice[region];e={'seasonal_ratio':b,'v4_hurdle_rich':t,'v7_embedding_mlp':n}[c['expert']]
            p[mask]=(1-c['weight'])*b[mask]+c['weight']*e[mask]
        actual=diagnostics(f,p);base=diagnostics(f,b)
        passed=actual['monthly_mae']<=.95*base['monthly_mae'] and actual['cell_month_mae']<=1.05*base['cell_month_mae'] and all(actual['regions'][r]['monthly_mae']<=1.05*base['regions'][r]['monthly_mae'] for r in ['north','south'])
        report['audits'][label]={'candidate':actual,'baseline':base,'passed':bool(passed)}
        out=f[['date','gy','gx','latitude','modis_count','viirs_count']].copy();out['candidate']=p;out['baseline']=b;out.to_csv(OUT/f'{label}_predictions.csv.gz',index=False,compression={'method':'gzip','mtime':0})
        print('AUDIT',label,round(actual['monthly_mae'],2),round(base['monthly_mae'],2),passed,flush=True)
    report['all_gates_passed']=all(x['passed'] for x in report['audits'].values());report['production_changed']=False
    save('report.json',report)


if __name__=='__main__':run()
