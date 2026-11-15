"""Conservative historical transfer mixture and portable offline inference."""
from pathlib import Path
import json,pickle
import numpy as np
import pandas as pd
from backend.harmonization_v2 import SeasonalRatio


class HistoricalTransfer:
    def __init__(self,baseline,learned,choice):self.baseline=baseline;self.learned=learned;self.choice=choice

    def predict(self,frame,apply_history_policy=True):
        baseline=self.baseline.predict(frame);learned=self.learned.predict(frame);result=baseline.copy()
        for region,mask in [('north',frame.latitude.to_numpy()>=39.5),('south',frame.latitude.to_numpy()<39.5)]:
            c=self.choice[region];expert={'seasonal_ratio':baseline,'v4_hurdle_rich':learned}.get(c['expert'])
            if expert is None:raise ValueError('Unpackaged expert selected')
            result[mask]=(1-c['weight'])*baseline[mask]+c['weight']*expert[mask]
        if apply_history_policy:
            # Operational configuration, not a trend predictor or a label-based
            # special case. Aqua starts in July2002; this regime is unsupported.
            early=pd.to_datetime(frame.date).lt('2002-07-01').to_numpy();result[early]=baseline[early]
        return result

    @classmethod
    def from_research(cls,root):
        root=Path(root);report=json.loads((root/'data/research/harmonization_release/report.json').read_text())
        with (root/'models/harmonization_v4/hurdle_rich.pkl').open('rb') as f:learned=pickle.load(f)
        with (root/'models/harmonization.pkl').open('rb') as f:original=pickle.load(f)
        baseline=SeasonalRatio();baseline.ratios=original['ratios'];baseline.global_ratio=float(np.mean(list(baseline.ratios.values())));baseline.state_ratios={}
        return cls(baseline,learned,report['choice'])
