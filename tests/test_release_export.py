import numpy as np
import pandas as pd
from backend.release_export import export_release


def test_release_preserves_partial_reference_outages_and_other_science():
    months=[];cells=[]
    for date,source,viirs,harmonized in [('2012-01-01','modeled_modis',3.,4.),('2012-02-01','observed_viirs',12.,12.),('2024-07-01','incomplete_reference',5.,None)]:
        year,month=map(int,[date[:4],date[5:7]])
        row={'date':date,'year':year,'month':month,'source':source,'modis_count':2.,'viirs_count':viirs,'harmonized_count':harmonized,
            'modeled_count':4.,'lower':None,'upper':None,'known_gap':harmonized is None,'reference_complete':source=='observed_viirs','modis_complete':True,
            'modis_missing_day_count':0,'viirs_missing_day_count':10 if harmonized is None else 0}
        months.append(row);cells.append({**row,'latitude':37.25,'longitude':-120.25})
    original={'harmonization':{'monthly':months,'cell_monthly':cells,'evaluation':{'metrics':{}},'limitations':[]},'extremes':{'p_value':.005},'provenance':{'preserve':True}}
    frame=pd.DataFrame(cells);frame.loc[frame.date.eq('2012-01-01'),'viirs_count']=np.nan
    calibration={'scale_power':.5,'regions':{'state':{'n_months':20,'quantiles':{'0.8':2.}}}}
    score={'monthly':[{'date':'2024-01-01','actual':2,'predicted':3}]}
    audit={key:{'candidate':score,'baseline':score} for key in ['selection','known_benchmark','backward']}
    report={'local_diagnostic_q80':2,'audits':audit,'choice':{},'all_gates_passed':True,'release_source_hashes':{},
        'uncertainty_assessment':{'known_benchmark':{'state':{'0.8':{'coverage':.8}}}}}
    bootstrap={'regions':{'state':[{'date':r['date'],'lower90':1,'upper90':10} for r in months]}}
    out=export_release(original,frame,[8.,8.,8.],calibration,report,bootstrap)
    assert out['extremes']==original['extremes'] and out['provenance']==original['provenance']
    h=out['harmonization'];assert h['monthly'][0]['harmonized_count']==8.
    assert h['monthly'][1]['harmonized_count']==12.
    assert h['monthly'][2]['harmonized_count'] is None and h['monthly'][2]['lower'] is None
    assert h['cell_monthly'][0]['viirs_count']==3. # partial startup preserved
    assert h['cell_monthly'][1]['harmonized_count']==12.
    assert h['cell_monthly'][2]['harmonized_count'] is None
    assert original['harmonization']['monthly'][0]['harmonized_count']==4. # no mutation
