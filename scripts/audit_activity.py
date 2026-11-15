#!/usr/bin/env python3
"""Disclose rolling-window sensor/rank agreement on a known later-year benchmark."""
from pathlib import Path
from datetime import date
import hashlib
import json
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
from backend.anomalies import EPOCH, WINDOWS, rolling, reference_weights, weighted_stats


def main():
    folder = ROOT / 'data/processed'
    with np.load(folder / 'activity_daily.npz', allow_pickle=False) as f:
        d = {k: f[k] for k in f.files}
    predicted = d['modis'].astype(float) * d['ratios'][d['season'], None]
    records = []
    for window in WINDOWS:
        model, model_valid = rolling(predicted, d['modis_valid'], window)
        observed, observed_valid = rolling(d['viirs'].astype(float), d['viirs_valid'], window)
        # Anchor grid frozen at fourteen-day spacing; no selection by errors or
        # fire size. Evaluation years are absent from sensor-ratio training.
        anchors = np.arange((date(2021,1,1)-EPOCH).days, len(model), 14)
        anchors = anchors[model_valid[anchors] & observed_valid[anchors]]
        anchors = anchors[d['years'][anchors-(window-1)//2] >= 2021]
        differences, agreements = [], []
        for anchor in anchors:
            weights, _ = reference_weights(d['years'], d['season'], observed_valid, anchor, window, 30)
            actual = weighted_stats(observed, observed[anchor], weights)
            estimate = weighted_stats(observed, model[anchor], weights)
            if actual is None:
                continue
            active = (observed[anchor] > 0) | (model[anchor] > 0)
            differences.extend(np.abs(actual[0][active] - estimate[0][active]).tolist())
            agreements.extend(((actual[0][active] >= 95) == (estimate[0][active] >= 95)).tolist())
        error = model[anchors] - observed[anchors]
        total = observed[anchors].sum()
        record = {'window_days': window, 'anchor_windows': int(len(anchors)),
                  'cell_mae': float(np.abs(error).mean()),
                  'statewide_mae': float(np.abs(error.sum(axis=1)).mean()),
                  'wape': float(np.abs(error).sum()/total) if total else None,
                  'active_score_mae': float(np.mean(differences)) if differences else None,
                  'active_outlier_agreement': float(np.mean(agreements)) if agreements else None,
                  'active_comparisons': len(differences)}
        records.append(record)
        print(json.dumps(record), flush=True)
    result = {'schema_version': 1, 'benchmark_years': [2021,2022,2023,2024,2025],
              'training_years': list(range(2013,2021)), 'threshold': 95, 'season_days': 30,
              'windows': records,
              'note': 'Ranks compare held-out MODIS estimates and observed VIIRS targets against the same VIIRS-only reference, excluding all calendar years touched by each target window. Measurement windows are wholly within 2021–2025. Active comparisons have reports in either sensor. Overlapping windows/cells are correlated; agreement is descriptive, not independent-trial accuracy. This already-inspected period is a known benchmark, not a pristine test or proof of pre-2012 transfer.',
              'daily_artifact_sha256': hashlib.sha256((folder/'activity_daily.npz').read_bytes()).hexdigest()}
    (folder/'activity_diagnostics.json').write_text(json.dumps(result, indent=2)+'\n')


if __name__ == '__main__':
    main()
