#!/usr/bin/env python3
"""Reproduce release metrics, interval diagnostics and prepared-data invariants."""
import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import pickle
import subprocess
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.harmonization_uncertainty import evaluate_bands
from scripts.train_harmonization_release import choose_weights
from scripts.train_harmonization_v2 import diagnostics, subset

OUT = ROOT / 'data/research/harmonization_release'
DATA = ROOT / 'data/processed'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def same_numbers(actual, expected):
    """Compare nested metric reports, allowing CSV round-trip precision."""
    if isinstance(expected, dict):
        assert actual.keys() == expected.keys()
        for key in expected:
            same_numbers(actual[key], expected[key])
    elif isinstance(expected, list):
        assert len(actual) == len(expected)
        for a, b in zip(actual, expected):
            same_numbers(a, b)
    elif isinstance(expected, (float, int)) and not isinstance(expected, bool):
        assert np.isclose(actual, expected, rtol=1e-9, atol=1e-8), (actual, expected)
    else:
        assert actual == expected


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--roundtrip', action='store_true', help='Verify exact local rollback and then reapply release')
    args = parser.parse_args()
    report = json.loads((OUT / 'report.json').read_text())
    selection = json.loads((OUT / 'training_selection.json').read_text())
    uncertainty = json.loads((OUT / 'uncertainty.json').read_text())
    original_bytes = gzip.decompress((OUT / 'original_analysis.json.gz').read_bytes())
    original = json.loads(original_bytes)
    assert report['protocol_sha256'] == sha(ROOT / 'research/harmonization_release/protocol.json')
    assert 'audits' not in selection and not selection['audit_years_used_for_selection']
    assert selection['choice'] == report['choice']
    pieces = []
    for fold in report['protocol']['meta_folds']:
        f = pd.read_csv(OUT / f'{fold["name"]}.csv.gz')
        assert f.year.between(*fold['predict']).all()
        assert set(range(fold['train'][0], fold['train'][1] + 1)).isdisjoint(f.year.unique())
        assert f.year.between(2013, 2020).all()
        pieces.append(f)
    choice, _ = choose_weights(pd.concat(pieces, ignore_index=True))
    same_numbers(choice, report['choice'])

    frame = pd.read_csv(ROOT / 'data/research/harmonization_v4/cells.csv.gz', dtype={'ecoregion': str})
    with (ROOT / 'models/harmonization_release/candidate.pkl').open('rb') as handle:
        package = pickle.load(handle)
    assert package['report_sha256'] == sha(OUT / 'report.json')
    model = package['model']
    prediction = model.predict(frame)
    assert np.isfinite(prediction).all() and (prediction >= 0).all()
    mutated = frame.copy()
    mutated['viirs_count'] = 123456789
    mutated['year'] = 1900
    np.testing.assert_array_equal(prediction, model.predict(mutated))

    for label, years in report['protocol']['audit_periods'].items():
        f = subset(frame, years).sort_values(['date', 'gy', 'gx'])
        p, b = model.predict(f), model.baseline.predict(f)
        saved = pd.read_csv(OUT / f'{label}_predictions.csv.gz')
        np.testing.assert_allclose(p, saved.candidate, rtol=1e-9, atol=1e-8)
        np.testing.assert_allclose(b, saved.baseline, rtol=1e-9, atol=1e-8)
        same_numbers(diagnostics(f, p), report['audits'][label]['candidate'])
        same_numbers(diagnostics(f, b), report['audits'][label]['baseline'])
        level = 'calibration' if label == 'selection' else label
        same_numbers(evaluate_bands(f, p, package['uncertainty']), uncertainty['assessment'][level])
    assert report['all_gates_passed']
    assert uncertainty['bootstrap']['cache_sha256'] == sha(OUT / 'bootstrap_predictions.npz')
    samples = np.load(OUT / 'bootstrap_predictions.npz')['prediction']
    assert samples.shape == (39, len(frame)) and np.isfinite(samples).all()
    dates = sorted(frame.date.unique())
    for region, mask in [('state', np.ones(len(frame), bool)), ('north', frame.latitude.to_numpy() >= 39.5), ('south', frame.latitude.to_numpy() < 39.5)]:
        totals = [pd.Series(p[mask], index=frame.loc[mask, 'date']).groupby(level=0).sum().reindex(dates).to_numpy() for p in samples]
        quantiles = np.quantile(totals, [.05, .5, .95], axis=0)
        saved = uncertainty['bootstrap']['regions'][region]
        for i, key in enumerate(['lower90', 'median', 'upper90']):
            np.testing.assert_allclose(quantiles[i], [r[key] for r in saved])

    roundtrip = False
    if args.roundtrip:
        before = json.loads((DATA / 'analysis.json').read_text())
        for arguments in [[], ['--restore'], []]:
            subprocess.run([sys.executable, str(ROOT / 'scripts/promote_historical_transfer.py'), *arguments], check=True, cwd=ROOT)
            if arguments:
                assert (DATA / 'analysis.json').read_bytes() == original_bytes
                assert (DATA / 'analysis.json.gz').read_bytes() == (OUT / 'original_runtime_analysis.json.gz').read_bytes()
                assert json.loads((ROOT / 'models/harmonization_release/active_manifest.json').read_text())['id'] == 'original-v1'
        after = json.loads((DATA / 'analysis.json').read_text())
        assert {k: v for k, v in before.items() if k != 'generated_at'} == {k: v for k, v in after.items() if k != 'generated_at'}
        roundtrip = True

    active_bytes = (DATA / 'analysis.json').read_bytes()
    active = json.loads(active_bytes)
    assert gzip.decompress((DATA / 'analysis.json.gz').read_bytes()) == active_bytes
    old, new = original['harmonization'], active['harmonization']
    assert new['release']['id'] == 'historical-transfer-1'
    assert len(new['monthly']) == 300 and len(new['cell_monthly']) == 67200
    assert sum(r['harmonized_count'] is None for r in new['monthly']) == 17
    assert {k: v for k, v in active.items() if k not in ['harmonization', 'generated_at']} == {k: v for k, v in original.items() if k not in ['harmonization', 'generated_at']}
    for a, b in zip(old['monthly'], new['monthly']):
        for key in ['date', 'modis_count', 'viirs_count', 'source', 'known_gap', 'reference_complete', 'modis_complete']:
            assert a[key] == b[key]
        if a['source'] != 'modeled_modis':
            assert a['harmonized_count'] == b['harmonized_count']
        if a['date'] < '2002-07-01':
            assert np.isclose(a['modeled_count'], b['modeled_count'])
        assert np.isclose(a['modeled_count'], b['baseline_modeled_count'])
    cells = pd.DataFrame(new['cell_monthly'])
    np.testing.assert_allclose(cells.modeled_count, prediction)
    north = frame.latitude.to_numpy() >= 39.5
    np.testing.assert_allclose(prediction[north], model.baseline.predict(frame)[north])
    sums = cells.groupby('date').harmonized_count.sum(min_count=1)
    np.testing.assert_allclose(sums, [r['harmonized_count'] if r['harmonized_count'] is not None else np.nan for r in new['monthly']], equal_nan=True)

    from fastapi.testclient import TestClient
    from backend.app import app
    with TestClient(app) as client:
        assert client.get('/api/health').json()['observations'] == 1169069
        catalog = client.get('/api/catalog').json()
        assert catalog['harmonization']['release']['id'] == 'historical-transfer-1'
        regional = client.get('/api/overview', params={'bbox': '-124,39.5,-120,42'}).json()
        assert all(r['lower'] is None and r['training_variability_lower90'] is None for r in regional['monthly'])
        csv = client.get('/api/export/monthly').text
        assert 'baseline_modeled_count' in csv.splitlines()[0]
    verification = {
        'verified_at': datetime.now(timezone.utc).isoformat(),
        'release': new['release']['id'], 'all_checks_passed': True,
        'checks': ['training-only OOF choice reproduced', 'disjoint whole-year folds', 'protocol and package hashes', 'saved predictions and all metric reports reproduced', 'reference/year input invariance', 'residual coverage reproduced', '39 block-bootstrap quantiles reproduced after aggregation', 'raw counts, observed reference, outage masks and other science preserved', 'Terra-only fallback unchanged', 'northern baseline exact', 'cell sums and packed runtime parity', 'real-data API and custom AOI interval scope', 'CSV baseline comparison'],
        'exact_rollback_and_reapply_verified': roundtrip,
        'artifacts': {str(p.relative_to(ROOT)): sha(p) for p in [DATA / 'analysis.json', DATA / 'analysis.json.gz', OUT / 'report.json', OUT / 'training_selection.json', OUT / 'uncertainty.json', OUT / 'bootstrap_predictions.npz', ROOT / 'models/harmonization_release/candidate.pkl']},
        'limits': ['Historical periods were repeatedly inspected, not a fresh independent test.', 'No verified predictive coverage before 2012; southern nominal 80% band undercovers the known benchmark.'],
    }
    (OUT / 'verification.json').write_text(json.dumps(verification, indent=2))
    print('PASS: release predictions, metrics, intervals, scientific invariants, API, and rollback/reapply' if roundtrip else 'PASS: release predictions, metrics, intervals, scientific invariants and API')


if __name__ == '__main__':
    main()
