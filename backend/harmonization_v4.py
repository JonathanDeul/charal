"""Exploratory monthly feature models, anchored to training-only calibration."""
import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor,HistGradientBoostingClassifier
from sklearn.linear_model import PoissonRegressor
from sklearn.preprocessing import StandardScaler
from backend.harmonization_v2 import SeasonalRatio,predictors,NUMERIC,BoostedCorrection

RICH=['subcell_occupancy','spatial_components','largest_component','largest_component_fraction',
    'frp_q25','frp_q50','frp_q90','contrast_mean','contrast_max','confidence_mean','daily_max','daily_concentration',
    'reports_per_occupied_subcell','neighbor1_modis_count','neighbor2_modis_count','neighbor1_frp_sum','neighbor2_frp_sum',
    'previous_modis_count','previous3_modis_count','previous_frp_sum','previous3_frp_sum']
SIMPLE=['log_modis','log_frp_mean','terra_fraction','day_fraction','footprint_mean','month_sin','month_cos']


def features(frame,rich=True):
    x=predictors(frame)
    cols=NUMERIC+['month_sin','month_cos','latitude','longitude'] if rich else SIMPLE
    a=x[cols].to_numpy(float)
    if rich:
        # Fixed transforms; no target-derived normalization or reference features.
        b=frame[RICH].to_numpy(float)
        b=np.sign(b)*np.log1p(np.abs(b))
        a=np.column_stack([a,b])
    return a


class OffsetModel:
    def __init__(self,family,penalty=1.):self.family=family;self.penalty=penalty

    def fit(self,frame):
        self.ratio=SeasonalRatio().fit(frame)
        x=features(frame,rich=self.family!='poisson_linear_simple');y=frame.viirs_count.to_numpy()
        exposure=self.ratio.predict(frame)+.05
        if self.family.startswith('poisson_linear'):
            self.scaler=StandardScaler().fit(x,sample_weight=exposure)
            x=self.scaler.transform(x)
            self.model=PoissonRegressor(alpha=self.penalty,max_iter=1000,tol=1e-7)
            self.model.fit(x,y/exposure,sample_weight=exposure)
        elif self.family=='hurdle_rich':
            self.classifier=HistGradientBoostingClassifier(max_iter=120,learning_rate=.035,max_leaf_nodes=7,
                min_samples_leaf=100,l2_regularization=10,early_stopping=False,random_state=42)
            self.classifier.fit(x,y>0)
            active=y>0
            self.model=HistGradientBoostingRegressor(loss='poisson',max_iter=120,learning_rate=.035,max_leaf_nodes=7,
                min_samples_leaf=100,l2_regularization=10,early_stopping=False,random_state=42)
            self.model.fit(x[active],y[active]/exposure[active],sample_weight=exposure[active])
        else:
            medium=self.family.endswith('medium')
            self.model=HistGradientBoostingRegressor(loss='poisson',max_iter=180 if medium else 120,
                learning_rate=.04 if medium else .035,max_leaf_nodes=15 if medium else 7,
                min_samples_leaf=60 if medium else 100,l2_regularization=10,early_stopping=False,random_state=42)
            self.model.fit(x,y/exposure,sample_weight=exposure)
        self.training_years=sorted(frame.year.unique().tolist());return self

    def predict(self,frame):
        x=features(frame,rich=self.family!='poisson_linear_simple')
        if hasattr(self,'scaler'):x=self.scaler.transform(x)
        rate=self.model.predict(x)
        if hasattr(self,'classifier'):rate*=self.classifier.predict_proba(x)[:,1]
        return (self.ratio.predict(frame)+.05)*rate


def make_model(family,penalty=1.):
    return BoostedCorrection() if family=='offset_boost_original' else OffsetModel(family,penalty)
