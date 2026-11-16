"""Shared evaluation and report generation for CLI and browser clients."""
import json
from datetime import datetime, timezone
from pathlib import Path

from .core import metrics


def build_report(trials, threshold, active_ids):
    if not trials:
        raise ValueError('Provide at least one evaluation image.')
    if not 0 < threshold < 1:
        raise ValueError('Threshold must be between 0 and 1.')
    active_ids = set(active_ids)
    if not active_ids:
        raise ValueError('Enroll at least one active resident first.')
    for trial in trials:
        expected = trial['expected_id']
        if expected is not None and expected not in active_ids:
            raise ValueError('Unknown/inactive expected_id: ' + str(expected))
    known = sum(t['expected_id'] is not None for t in trials)
    return dict(created_at=datetime.now(timezone.utc).isoformat(), threshold=threshold,
                active_residents=len(active_ids), known_trials=known, unknown_trials=len(trials)-known,
                warnings=[] if 0 < known < len(trials) else ['Include both registered residents and unknown visitors to measure both error rates.'],
                metrics=metrics([(t['expected_id'],t['resident_id']) for t in trials]), trials=trials)


def markdown_report(report):
    lines = ['# Smart Society — Measured Evaluation', '',
             f"Created: {report['created_at']}", f"Active residents: {report['active_residents']}",
             f"Threshold: {report['threshold']}", f"Known trials: {report['known_trials']}",
             f"Unknown trials: {report['unknown_trials']}", '', '| Metric | Value |', '| --- | --- |']
    for key, value in report['metrics'].items():
        display = 'N/A (zero denominator)' if value is None else str(round(value, 6))
        lines.append(f'| {key} | {display} |')
    lines += ['', *report['warnings'], '',
              'Entry metrics measure known versus unknown access. Identity accuracy also penalizes wrong-resident matches.',
              'Images must be held out from enrollment and threshold calibration. These results describe only the supplied test set.',
              'No liveness detection is provided. This academic prototype does not control a physical gate.']
    return '\n'.join(lines) + '\n'


def save_report(report, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    (output/'evaluation.json').write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
    (output/'evaluation.md').write_text(markdown_report(report), encoding='utf-8')
