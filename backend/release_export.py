"""Build a deployment-safe artifact without loading training libraries at runtime."""
from copy import deepcopy
import numpy as np
import pandas as pd
from backend.harmonization_uncertainty import band_bounds


def export_release(original,frame,prediction,calibration,report,bootstrap):
    output=deepcopy(original);old=original['harmonization'];h=deepcopy(old)
    f=frame.copy();f['prediction']=np.asarray(prediction,float)
    if not np.isfinite(f.prediction).all() or (f.prediction<0).any():raise ValueError('Invalid release predictions')
    if f.duplicated(['date','latitude','longitude']).any():raise ValueError('Duplicate cell-month predictions')
    old_months={r['date']:r for r in old['monthly']}
    raw_reference={(r['date'],r['latitude'],r['longitude']):r['viirs_count'] for r in old['cell_monthly']}
    baseline_reference={(r['date'],r['latitude'],r['longitude']):r['modeled_count'] for r in old['cell_monthly']}
    cell_q=report['local_diagnostic_q80']
    cells=[]
    for r in f.to_dict('records'):
        base=old_months[r['date']];modeled=base['source']=='modeled_modis';available=base['harmonized_count'] is not None
        key=(r['date'],r['latitude'],r['longitude'])
        reference=raw_reference.get(key,None if r['year']<2012 else 0.)
        early=r['date']<'2002-07-01'
        width=cell_q*np.sqrt(r['prediction']+1)
        cells.append({'date':r['date'],'year':int(r['year']),'month':int(r['month']),
            'latitude':r['latitude'],'longitude':r['longitude'],'modis_count':r['modis_count'],'viirs_count':reference,
            'modeled_count':r['prediction'],'baseline_modeled_count':baseline_reference.get(key,0.),
            'harmonized_count':None if not available else r['prediction'] if modeled else reference,
            'source':base['source'],'lower':max(0,r['prediction']-width) if modeled and available else None,
            'upper':r['prediction']+width if modeled and available else None,
            'model_component':'terra_only_baseline_fallback' if early else 'seasonal_ratio' if r['latitude']>=39.5 else 'conditional_boosted_mean',
            'known_gap':base['known_gap'],'reference_complete':base['reference_complete'],'modis_complete':base['modis_complete'],
            'modis_missing_day_count':base['modis_missing_day_count'],'viirs_missing_day_count':base['viirs_missing_day_count']})
    totals=f.groupby('date').prediction.sum().to_dict();months=[]
    bootstrap_state={r['date']:r for r in bootstrap['regions']['state']}
    for previous in old['monthly']:
        r=deepcopy(previous);date=r['date'];p=float(totals[date]);modeled=r['source']=='modeled_modis' and r['harmonized_count'] is not None
        r['baseline_modeled_count']=previous['modeled_count'];r['modeled_count']=p
        if modeled:
            r['harmonized_count']=p;lo,hi=band_bounds(np.array([p]),calibration,'state',.8);r['lower']=float(lo[0]);r['upper']=float(hi[0])
        else:r['lower']=None;r['upper']=None
        r['sampling_regime']='terra_only' if date<'2002-07-01' else 'terra_aqua'
        r['uncertainty_status']='unvalidated_terra_only_baseline_fallback' if date<'2002-07-01' else 'unvalidated_historical_transfer' if date<'2012-02-01' else 'observed_reference_or_known_gap'
        r['training_variability_lower90']=bootstrap_state[date]['lower90'] if modeled else None
        r['training_variability_upper90']=bootstrap_state[date]['upper90'] if modeled else None
        months.append(r)
    evaluation=deepcopy(old['evaluation']);evaluation['legacy_v1']=deepcopy(old['evaluation'])
    evaluation['selected_method']='historical_transfer'
    evaluation['selection_rule']='Regional expert and weight selected on2013-2020 forward/backward out-of-fit errors; later periods are known audits, not an untouched test.'
    evaluation['metrics']={'historical_transfer':report['audits']['known_benchmark']['candidate'],'baseline':report['audits']['known_benchmark']['baseline']}
    evaluation['validation_metrics']={'historical_transfer':report['audits']['selection']['candidate'],'baseline':report['audits']['selection']['baseline']}
    evaluation['backward_check']=report['audits']['backward']
    evaluation['test_status']='previously_inspected_benchmark';evaluation['training_selection']=report['choice']
    candidate=report['audits']['known_benchmark']['candidate']['monthly'];baseline=report['audits']['known_benchmark']['baseline']['monthly']
    evaluation['monthly_test']=[{'date':a['date'],'actual':a['actual'],'historical_transfer':a['predicted'],'baseline':b['predicted']} for a,b in zip(candidate,baseline)]
    h.update({'monthly':months,'cell_monthly':cells,'evaluation':evaluation,
        'model':{'type':'HistoricalTransfer','label':'Conservative regional transfer','components':report['choice'],
            'latitude_boundary':39.5,'training_years':list(range(2013,2021)),'version':'historical-transfer-1',
            'features':['MODIS counts and FRP','Detected-pixel geometry/time','Within-cell cluster structure','MODIS spatial and historical context','Calendar month and location']},
        'uncertainty':{'label':'80% empirical aggregate-residual band','calibration_months':calibration['regions']['state']['n_months'],
            'scale_power':calibration['scale_power'],'aggregate_calibration':calibration,
            'test_monthly_band_coverage':report['uncertainty_assessment']['known_benchmark']['state']['0.8']['coverage'],
            'assessment':report['uncertainty_assessment'],'local_diagnostic_q80':cell_q,
            'note':'Residual bands quantify disagreement with SNPP counts. No guaranteed coverage before2012. Local diagnostic bands must not be summed. Bootstrap ranges describe training-data variability separately.'},
        'interval_description':'The shaded statewide band summarizes calibrated reference-scale residuals. Historical transfer bias is not fully quantified. Before July2002 the original Terra-only baseline estimate is retained and explicitly flagged.',
        'release':{'id':'historical-transfer-1','all_gates_passed':report['all_gates_passed'],'source_hashes':report['release_source_hashes'],
            'historical_policy':'Original baseline before Aqua operation July2002. Observed SNPP fromFebruary2012 unchanged; known gaps remain null.'}})
    h['limitations']=list(old['limitations'])+[
        'The active model mixes a northern seasonal calibration with a southern conditional-count learner selected only on training-period out-of-fit tests.',
        'All historical audit years have been inspected; repeated development limits independent validation claims.',
        'The fixed latitude39.5 mixture boundary can introduce a model-regime discontinuity; original point observations are never moved or reconstructed.',
        'The80% residual band undercovers the southern aggregate on the known benchmark; see explicit regional coverage diagnostics.',
        'Before July2002, no learned dual-platform correction is applied. The original Terra-only estimate remains an unvalidated sampling-regime extrapolation.']
    output['harmonization']=h
    return output
