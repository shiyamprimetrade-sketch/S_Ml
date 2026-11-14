"""Reproducible synthetic control-flow demo; never a TikTok accuracy benchmark."""
import json
from pathlib import Path
import tempfile
import numpy as np
from s_ml.storage import Store
from s_ml.promotion import train_and_gate, active_model, rollback


def demonstration():
    train_x = np.linspace(-1, 1, 80).reshape(-1, 1)
    decisions = []
    with tempfile.TemporaryDirectory() as folder, Store(Path(folder) / 'lab.sqlite3') as store:
        for index, (version, slope) in enumerate([('initial', 1.4), ('better', 1.9), ('worse', 1.2)]):
            rng = np.random.default_rng(27 + index)
            x = rng.uniform(-1, 1, size=(40, 1))
            manifest = {'schema': 's_ml.training-gate.v1', 'mission': 'synthetic-control',
                        'version': version, 'validation_mode': 'iid',
                        'training': {'x': train_x.tolist(), 'y': (3 + slope * train_x[:, 0]).tolist(),
                                     'ids': [f'training-{i}' for i in range(80)], 'feature_schema': ['x']},
                        'evaluation': {'x': x.tolist(), 'y': (3 + 2 * x[:, 0]).tolist(),
                                       'ids': [f'fresh-round-{index}-{i}' for i in range(40)]}}
            result = train_and_gate(store, manifest, Path(folder) / 'artifacts')
            decisions.append(result['promotion'])
        assert [d['accepted'] for d in decisions] == [True, True, False]
        retained = active_model(store, 'synthetic-control')[0]
        assert retained == 'better'
        rollback_result = rollback(store, 'synthetic-control', 'initial')
        assert active_model(store, 'synthetic-control')[0] == 'initial'
    return {'scope': 'Synthetic control-flow demonstration; no platform performance claim',
            'decisions': decisions, 'active_after_rejected_candidate': retained, 'rollback': rollback_result}


if __name__ == '__main__':
    print(json.dumps(demonstration(), indent=2))
