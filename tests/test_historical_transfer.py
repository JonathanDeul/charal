import numpy as np
import pandas as pd
from backend.historical_transfer import HistoricalTransfer


class FixedExpert:
    def __init__(self,factor):self.factor=factor
    def predict(self,frame):return frame.modis_count.to_numpy()*self.factor


def test_transfer_retains_north_and_pre_aqua_fallback_without_reference_inputs():
    model=HistoricalTransfer(FixedExpert(2),FixedExpert(3),{'north':{'expert':'seasonal_ratio','weight':0},'south':{'expert':'v4_hurdle_rich','weight':1}})
    f=pd.DataFrame({'date':['2010-01-01','2010-01-01','2001-01-01'],'latitude':[40.,37.,37.],'modis_count':[4.,4.,4.],
        'viirs_count':[0,100,1],'year':[2010,2010,2001]})
    np.testing.assert_array_equal(model.predict(f),[8,12,8])
    np.testing.assert_array_equal(model.predict(f.assign(viirs_count=1e9,year=1800)),[8,12,8])


def test_custom_aoi_does_not_inherit_statewide_bootstrap_range(monkeypatch):
    import backend.app as api
    monthly=[{'date':'2010-01-01','year':2010,'month':1,'modis_count':3,'viirs_count':None,'harmonized_count':8,'modeled_count':8,
        'baseline_modeled_count':6,'source':'modeled_modis','lower':1,'upper':15,'training_variability_lower90':2,'training_variability_upper90':12}]
    cells=[{**monthly[0],'latitude':37.25,'longitude':-120.25,'modis_count':1,'harmonized_count':3,'modeled_count':3,'baseline_modeled_count':2}]
    monkeypatch.setattr(api,'dataset',lambda:{'analysis':{'harmonization':{'monthly':monthly,'cell_monthly':cells}}})
    api.selected_months.cache_clear()
    try:
        row=api.selected_months(2010,2010,(-121,37,-120,38))[0]
        assert row['harmonized_count']==3 and row['baseline_modeled_count']==2
        assert row['lower'] is None and row['upper'] is None
        assert row['training_variability_lower90'] is None and row['training_variability_upper90'] is None
        assert 'No calibrated' in row['interval_scope']
    finally:api.selected_months.cache_clear()
