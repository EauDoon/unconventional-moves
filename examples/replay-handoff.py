#!/usr/bin/env python3
"""Replay synthetic handoff recovery offline. No real experiment is executed."""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replay(output: Path) -> dict:
    output.mkdir()  # A fresh directory is mandatory; never replace prior work.

    def run(*args, expected=0):
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/moves.py'), *map(str, args)],
                                capture_output=True, text=True, encoding='utf-8')
        if result.returncode != expected:
            raise RuntimeError(f'Unexpected exit {result.returncode}: {result.stderr}')
        return result

    def read(name):
        return json.loads((output / name).read_text(encoding='utf-8'))

    def write(name, value):
        with (output / name).open('x', encoding='utf-8', newline='\n') as handle:
            handle.write(json.dumps(value, indent=2) + '\n')

    run('init', '--output', output / 'draft.json')
    run('select', output / 'draft.json', '--move-id', 'move-01',
        '--reason', 'Synthetic replay: review cue timing first',
        '--first-step', 'Review the private practice setup; no activity is performed',
        '--output', output / 'selected.json')
    run('card', output / 'selected.json', '--output', output / 'card.json')
    run('observation-draft', output / 'selected.json', '--output', output / 'observation-draft.json')
    draft = read('observation-draft.json')
    target = read('card.json')['experiment']['target']
    history = []
    for index, value in enumerate([None, 0, target], 1):
        observation = {**draft, 'elapsed_hours': index, 'active_minutes': index,
                       'observed_value': value, 'stop_triggered': index == 1,
                       'notes': f'Synthetic checkpoint {index}; no experiment occurred. ' +
                                ('Declared stop; measurement unavailable.' if index == 1 else
                                 'After the earlier stop; this does not permit continuation.')}
        write(f'observation-{index}.json', observation)
        args = ['record', output / 'selected.json', output / f'observation-{index}.json']
        if history:
            args += ['--history', output / f'checkpoints-{index - 1}.json']
        run(*args, '--output', output / f'checkpoints-{index}.json')
        history.append(observation)
    run('handoff', output / 'selected.json', '--timeline', output / 'checkpoints-3.json',
        '--output', output / 'handoff.json')
    run('verify-handoff', output / 'handoff.json')
    restored = output / 'restored'
    run('unpack-handoff', output / 'handoff.json', '--output-dir', restored)
    plan, checkpoints = restored / 'plan.json', restored / 'checkpoints.json'
    report = read('restored/resume-review.json')
    if read('restored/plan.json') != read('selected.json') or read('restored/checkpoints.json') != history:
        raise RuntimeError('Restored source records changed')
    if (report['decision'] != 'stop_and_review' or report['first_stop_checkpoint'] != 1
            or not report['timeline_review']['measurement_summary']['latest_checkpoint_target_met']):
        raise RuntimeError('Later numeric target hid an earlier stop')
    run('timeline', plan, checkpoints, '--format', 'csv', '--output', output / 'checkpoints.csv')
    run('render', plan, '--format', 'html', '--output', output / 'review.html')
    run('debrief', plan, checkpoints, '--output', output / 'debrief.md')
    with (output / 'checkpoints.csv').open(encoding='utf-8', newline='') as handle:
        rows = list(csv.DictReader(handle))
    if [row['measurement_available'] for row in rows] != ['False', 'True', 'True']:
        raise RuntimeError('Missing measurement was not preserved')
    if rows[1]['observed_value'] != '0' or rows[-1]['decision'] != "'stop_and_review":
        raise RuntimeError('CSV lost zero or persistent stop')
    # Recording another supplied synthetic entry does not authorize activity.
    write('observation-4.json', {**history[-1], 'elapsed_hours': 4, 'active_minutes': 4,
                                'notes': 'Synthetic later record only, after the stop; no experiment occurred.'})
    run('record', plan, output / 'observation-4.json', '--history', checkpoints,
        '--output', output / 'checkpoints-4.json')
    run('handoff', plan, '--timeline', output / 'checkpoints-4.json',
        '--output', output / 'next-handoff.json')
    run('verify-handoff', output / 'next-handoff.json')
    next_timeline = read('next-handoff.json')['timeline_review']
    if next_timeline['decision'] != 'stop_and_review' or not next_timeline['checkpoints'][-1]['after_stop']:
        raise RuntimeError('Appended record cleared a persistent stop')
    run('select', plan, '--move-id', 'move-02', '--reason', 'Synthetic revision for separate review',
        '--first-step', 'Review the alternative; no new trial is approved', '--output', output / 'revised.json')
    run('compare', plan, output / 'revised.json', '--output', output / 'revision-review.json')
    rejection = run('timeline', output / 'revised.json', checkpoints, expected=1)
    if 'current plan revision' not in rejection.stderr:
        raise RuntimeError('Expected rejection of old history with a new revision')
    run('observation-draft', output / 'revised.json', '--output', output / 'new-revision-draft.json')
    summary = {'synthetic_only': True, 'real_experiment_executed': False,
               'restored_checkpoints': len(history), 'first_stop_checkpoint': report['first_stop_checkpoint'],
               'decision': report['decision'], 'later_target_met': True,
               'missing_measurement_preserved': True, 'measured_zero_preserved': True,
               'appended_record_retains_stop': True, 'old_history_rejected_for_revision': True,
               'human_review_required': True,
               'limitation': 'This verifies record handling only, not usefulness, truth, consent, approval, or causation.'}
    write('replay-summary.json', summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='New directory inside an existing parent')
    args = parser.parse_args()
    try:
        summary = replay(args.output)
    except (OSError, ValueError, RuntimeError) as exc:
        print('FAIL ' + str(exc), file=sys.stderr)
        return 1
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
