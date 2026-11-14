"""Persistent regression promotion gate. Only this module changes active pointers.

Prepared dataset provenance is a trust boundary: IDs and timestamps must be
truthful and supplied by the training/collection pipeline. The gate cannot prove
that an external model never saw undeclared data. Metric gains are measurements,
not a guarantee that future predictions cannot get worse.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import uuid
import numpy as np
from .core import LinearGD, matrix, targets
from .ingestion import aware_time


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,100}', value):
        raise ValueError('Use a nonempty mission/version identifier without path separators')
    return value


def sample_ids(values, count):
    if (not isinstance(values, list) or len(values) != count or
        any(not isinstance(v, str) or not 1 <= len(v) <= 200 for v in values) or len(set(values)) != count):
        raise ValueError('One unique nonempty stable sample ID is required per row')
    return values


@dataclass(frozen=True)
class GatePolicy:
    min_examples: int = 30
    min_relative_improvement: float = .05
    max_rmse_ratio: float = 1.0
    min_absolute_improvement: float = 1e-8

    def __post_init__(self):
        if not isinstance(self.min_examples, int) or self.min_examples < 2:
            raise ValueError('Minimum sample count must be at least two')
        if not np.isfinite(self.min_relative_improvement) or not 0 < self.min_relative_improvement < 1:
            raise ValueError('Require a positive relative improvement below one')
        if not np.isfinite(self.min_absolute_improvement) or self.min_absolute_improvement <= 0:
            raise ValueError('Absolute improvement must be positive and finite')
        if not np.isfinite(self.max_rmse_ratio) or not 0 < self.max_rmse_ratio <= 1:
            raise ValueError('RMSE may not regress')


def register_checkpoint(store, mission, version, checkpoint, training_ids, training_y,
                        feature_schema, training_cutoff=None, validation_mode='temporal', account_id=None):
    identifier(mission)
    identifier(version)
    y = targets(training_y, len(training_ids))
    sample_ids(training_ids, len(y))
    if not len(y):
        raise ValueError('Training data must be nonempty')
    data = json.loads(Path(checkpoint).read_text(encoding='utf-8'))
    model = LinearGD.from_dict(data)
    if (not isinstance(feature_schema, list) or len(feature_schema) != len(model.mean) or
        len(set(feature_schema)) != len(feature_schema) or
        any(not isinstance(n, str) or not n for n in feature_schema)):
        raise ValueError('Named feature schema must match the trained checkpoint')
    if validation_mode not in ('iid', 'temporal') or (account_id is not None and validation_mode != 'temporal'):
        raise ValueError('Account forecasting requires temporal validation')
    cutoff = aware_time(training_cutoff).isoformat() if training_cutoff else None
    if validation_mode == 'temporal' and cutoff is None:
        raise ValueError('Temporal models require last training-label availability time')
    content = json.dumps(data, sort_keys=True, allow_nan=False)
    digest = hashlib.sha256(content.encode()).hexdigest()
    values = (mission, version, account_id, content, digest, json.dumps(feature_schema),
              json.dumps(training_ids), cutoff, validation_mode, float(np.mean(y)))
    db = store.connection
    with db:
        existing = db.execute('SELECT * FROM model_versions WHERE mission=? AND version=?', (mission, version)).fetchone()
        if existing:
            if tuple(existing) != values:
                raise ValueError('Model versions are immutable; register a new version')
            return digest
        mission_row = db.execute('SELECT * FROM model_versions WHERE mission=? LIMIT 1', (mission,)).fetchone()
        if mission_row and (mission_row['account_id'] != account_id or mission_row['validation_mode'] != validation_mode):
            raise ValueError('Mission ownership and validation mode cannot change')
        db.execute('INSERT INTO model_versions VALUES (?,?,?,?,?,?,?,?,?,?)', values)
    return digest


def metric_errors(y, prediction):
    error = y - prediction
    if not np.isfinite(error).all():
        raise ValueError('Predictions must be finite')
    return {'mae': float(np.mean(np.abs(error))), 'rmse': float(np.sqrt(np.mean(error ** 2)))}


def model_from_row(row):
    content = row['checkpoint']
    if hashlib.sha256(content.encode()).hexdigest() != row['digest']:
        raise ValueError('Checkpoint digest mismatch')
    return LinearGD.from_dict(json.loads(content))


def evaluate_and_promote(store, mission, version, x, y, heldout_ids,
                         label_available_at=None, policy=None, prediction_at=None):
    """Measure on fresh held-out labels; commit decision and active pointer atomically.

    Temporal labels must be available strictly after all training labels for both
    competing models. Once scored, samples cannot be reused for another decision
    in the mission, whether the candidate was accepted or rejected.
    """
    identifier(mission)
    identifier(version)
    policy = policy or GatePolicy()
    x = matrix(x)
    y = targets(y, len(x))
    sample_ids(heldout_ids, len(y))
    db = store.connection
    db.execute('BEGIN IMMEDIATE')
    try:
        candidate = db.execute('SELECT * FROM model_versions WHERE mission=? AND version=?', (mission, version)).fetchone()
        if candidate is None:
            raise ValueError('Candidate must be registered before evaluation')
        active = db.execute('''SELECT v.* FROM model_active a JOIN model_versions v
            ON v.mission=a.mission AND v.version=a.version WHERE a.mission=?''', (mission,)).fetchone()
        previous = active['version'] if active else None
        report = {'mission': mission, 'candidate': version, 'previous_version': previous,
                  'policy': asdict(policy), 'examples': len(y), 'accepted': False,
                  'holdout_sha256': hashlib.sha256(json.dumps({'ids': heldout_ids,
                      'x': x.tolist(), 'y': y.tolist(), 'label_available_at': label_available_at, 'prediction_at': prediction_at},
                      sort_keys=True, allow_nan=False).encode()).hexdigest(),
                  'limitation': 'Held-out improvements do not guarantee future performance'}
        reason = None
        scored = False
        if previous == version:
            reason = 'candidate_already_active'
        elif len(y) < policy.min_examples:
            reason = 'insufficient_heldout_examples'
        elif len(json.loads(candidate['feature_schema'])) != x.shape[1]:
            reason = 'feature_schema_mismatch'
        elif active and active['feature_schema'] != candidate['feature_schema']:
            reason = 'feature_schema_mismatch'
        elif set(heldout_ids) & set(json.loads(candidate['training_ids'])):
            reason = 'candidate_training_overlap'
        elif active and set(heldout_ids) & set(json.loads(active['training_ids'])):
            reason = 'incumbent_training_overlap'
        elif any(db.execute('SELECT 1 FROM model_holdouts WHERE mission=? AND example_id=?',
                            (mission, key)).fetchone() for key in heldout_ids):
            reason = 'holdout_already_scored'
        if reason is None and candidate['validation_mode'] == 'temporal':
            if not isinstance(label_available_at, list) or len(label_available_at) != len(y):
                reason = 'label_availability_required'
            else:
                times = [aware_time(t) for t in label_available_at]
                cutoffs = [aware_time(candidate['training_cutoff'])]
                if active:
                    cutoffs.append(aware_time(active['training_cutoff']))
                if max(times) > datetime.now(timezone.utc):
                    reason = 'labels_not_yet_available'
                elif min(times) <= max(cutoffs):
                    reason = 'training_label_time_overlap'
                elif not isinstance(prediction_at, list) or len(prediction_at) != len(y):
                    reason = 'prediction_origins_required'
                else:
                    origins = [aware_time(t) for t in prediction_at]
                    if origins != sorted(origins):
                        reason = 'heldout_not_chronological'
                    elif min(origins) <= max(cutoffs):
                        reason = 'forecast_origin_before_training_cutoff'
                    elif any(label < origin for label, origin in zip(times, origins)):
                        reason = 'label_before_forecast_origin'
        if reason is None:
            candidate_scores = metric_errors(y, model_from_row(candidate).predict(x))
            baseline_scores = metric_errors(y, np.full(len(y), candidate['baseline_mean']))
            references = {'baseline': baseline_scores}
            if active:
                references['incumbent'] = metric_errors(y, model_from_row(active).predict(x))
            report.update(candidate_scores=candidate_scores, reference_scores=references)
            scored = True
            for name, scores in references.items():
                if (candidate_scores['mae'] >= scores['mae'] * (1 - policy.min_relative_improvement) or
                    scores['mae'] - candidate_scores['mae'] <= policy.min_absolute_improvement):
                    reason = f'no_required_mae_improvement_over_{name}'
                    break
                if candidate_scores['rmse'] > scores['rmse'] * policy.max_rmse_ratio:
                    reason = f'rmse_regression_against_{name}'
                    break
            if reason is None:
                report['accepted'] = True
                reason = 'all_promotion_checks_passed'
        report['reason'] = reason
        now = datetime.now(timezone.utc).isoformat()
        decision = db.execute('''INSERT INTO model_decisions(mission,candidate,previous_version,kind,accepted,reason,report,at)
            VALUES (?,?,?,'promotion',?,?,?,?)''',
            (mission, version, previous, int(report['accepted']), reason, json.dumps(report, allow_nan=False), now))
        if scored:
            db.executemany('INSERT INTO model_holdouts VALUES (?,?,?)',
                           [(mission, key, decision.lastrowid) for key in heldout_ids])
        if report['accepted']:
            db.execute('''INSERT INTO model_active VALUES (?,?) ON CONFLICT(mission)
                DO UPDATE SET version=excluded.version''', (mission, version))
        db.commit()
        return report
    except BaseException:
        db.rollback()
        raise


def active_model(store, mission):
    row = store.connection.execute('''SELECT v.* FROM model_active a JOIN model_versions v
        ON a.mission=v.mission AND a.version=v.version WHERE a.mission=?''', (mission,)).fetchone()
    if row is None:
        return None
    return row['version'], model_from_row(row)


def rollback(store, mission, target_version):
    """Explicit restore to a previously gate-approved version; never an untested candidate."""
    db = store.connection
    db.execute('BEGIN IMMEDIATE')
    try:
        prior = db.execute('SELECT version FROM model_active WHERE mission=?', (mission,)).fetchone()
        approved = db.execute('''SELECT 1 FROM model_decisions WHERE mission=? AND candidate=?
            AND kind='promotion' AND accepted=1''', (mission, target_version)).fetchone()
        target = db.execute('SELECT * FROM model_versions WHERE mission=? AND version=?', (mission, target_version)).fetchone()
        if prior is None or target is None or not approved or prior[0] == target_version:
            raise ValueError('Choose a different, previously gate-approved version')
        model_from_row(target)  # Verify artifact integrity before changing the pointer.
        report = {'mission': mission, 'previous_version': prior[0], 'restored_version': target_version}
        db.execute('UPDATE model_active SET version=? WHERE mission=?', (target_version, mission))
        db.execute('''INSERT INTO model_decisions(mission,candidate,previous_version,kind,accepted,reason,report,at)
            VALUES (?,?,?,'rollback',1,'explicit_rollback',?,?)''',
            (mission, target_version, prior[0], json.dumps(report), datetime.now(timezone.utc).isoformat()))
        db.commit()
        return report
    except BaseException:
        db.rollback()
        raise


def registry_status(store):
    return {'active': [dict(r) for r in store.connection.execute('''SELECT a.mission,a.version,v.digest
        FROM model_active a JOIN model_versions v ON v.mission=a.mission AND v.version=a.version''')],
            'decisions': store.connection.execute('SELECT COUNT(*) FROM model_decisions').fetchone()[0],
            'recent_decisions': [dict(r) for r in store.connection.execute(
                'SELECT id,mission,candidate,previous_version,kind,accepted,reason,at FROM model_decisions ORDER BY id DESC LIMIT 10')]}


def train_and_gate(store, manifest, artifact_dir):
    """Train a prepared regression dataset, save a candidate, and run the gate.

    This function can be called by an authorized scheduler. It does not collect
    platform data or infer trustworthy horizon labels from arbitrary snapshots.
    """
    allowed = {'schema', 'mission', 'version', 'training', 'evaluation',
               'validation_mode', 'account_id', 'parameters'}
    if not isinstance(manifest, dict) or set(manifest) - allowed or manifest.get('schema') != 's_ml.training-gate.v1':
        raise ValueError('Unsupported prepared training manifest')
    mission, version = identifier(manifest['mission']), identifier(manifest['version'])
    if store.connection.execute('SELECT 1 FROM model_versions WHERE mission=? AND version=?', (mission, version)).fetchone():
        raise ValueError('Register each training run with a new immutable version')
    train, evaluation = manifest['training'], manifest['evaluation']
    x = matrix(train['x'])
    y = targets(train['y'], len(x))
    sample_ids(train['ids'], len(y))
    model = LinearGD(**manifest.get('parameters', {})).fit(x, y)
    folder = Path(artifact_dir)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f'{mission}_{version}_{uuid.uuid4().hex}.json'
    model.save(path)
    digest = register_checkpoint(store, mission, version, path, train['ids'], y,
                                 train['feature_schema'], train.get('label_available_until'),
                                 manifest.get('validation_mode', 'temporal'), manifest.get('account_id'))
    report = evaluate_and_promote(store, mission, version, evaluation['x'], evaluation['y'], evaluation['ids'],
                                  evaluation.get('label_available_at'), prediction_at=evaluation.get('prediction_at'))
    return {'checkpoint': str(path), 'checkpoint_sha256': digest,
            'initial_training_loss': model.history[0], 'final_training_loss': model.history[-1],
            'promotion': report}
