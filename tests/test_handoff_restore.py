"""Verified handoff recovery must retain the entire supplied experiment history."""
import copy
import csv
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import moves


class HandoffRestoreTests(unittest.TestCase):
    def setUp(self):
        self.plan = moves.read_plan(ROOT / 'examples/bounded-plan.json')
        self.plan['moves'][0]['experiment']['exposure'] = 'consenting_participants'
        first = {**moves.observation_draft(self.plan), 'elapsed_hours': 1,
                 'active_minutes': 1, 'stop_triggered': True,
                 'notes': 'Synthetic missing measurement and unconfirmed consent.'}
        self.history = [first,
                        {**first, 'elapsed_hours': 2, 'active_minutes': 2,
                         'observed_value': 0, 'stop_triggered': False,
                         'consent_confirmed': True, 'notes': '=Synthetic zero, not missing'},
                        {**first, 'elapsed_hours': 3, 'active_minutes': 3,
                         'observed_value': moves.selected_move(self.plan)['experiment']['target'],
                         'stop_triggered': False, 'consent_confirmed': True,
                         'notes': '<script>synthetic</script> Later target after stop.'}]

    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(ROOT / 'scripts/moves.py'), *map(str, args)],
                              capture_output=True, text=True)

    def test_restore_preserves_exact_plan_all_records_and_cumulative_stop(self):
        # Numeric spelling and authored strings must survive parsed-JSON bindings.
        self.plan['moves'][0]['experiment']['baseline'] = -0.0
        for row in self.history:
            row['plan_sha256'] = moves.plan_digest(self.plan)
        bundle = moves.timeline_handoff(self.plan, self.history)
        original = copy.deepcopy(bundle)
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / 'restored'
            report = moves.unpack_handoff(bundle, output)
            plan = moves.read_plan(output / 'plan.json')
            history = moves.read_json_file(output / 'checkpoints.json')
            self.assertEqual(moves.canonical_json(plan), moves.canonical_json(self.plan))
            self.assertEqual(moves.canonical_json(history), moves.canonical_json(self.history))
            self.assertEqual(moves.plan_digest(plan), bundle['plan_sha256'])
            self.assertEqual(report['checkpoint_count'], 3)
            self.assertEqual(report['decision'], 'stop_and_review')
            self.assertEqual(report['first_stop_checkpoint'], 1)
            self.assertTrue(report['observations_after_stop'])
            self.assertEqual(report['reasons'], ['consent_not_confirmed', 'declared_stop_condition_triggered'])
            self.assertTrue(report['human_review_required'])
            self.assertEqual(report['timeline_review'], moves.review_timeline(plan, history))
            self.assertEqual(moves.read_json_file(output / 'resume-review.json'), report)
            self.assertEqual(moves.read_json_file(output / 'handoff.json'), bundle)
            self.assertTrue(moves.verify_handoff(moves.read_json_file(output / 'handoff.json'))['consistent'])
            rows = list(csv.DictReader(io.StringIO(moves.timeline_csv(plan, history))))
            self.assertEqual([r['measurement_available'] for r in rows], ['False', 'True', 'True'])
            self.assertEqual([r['observed_value'] for r in rows], ['', '0', str(self.history[2]['observed_value'])])
            self.assertEqual(rows[1]['notes'], "'" + self.history[1]['notes'])
            self.assertNotIn('<script>', moves.render_debrief(plan, history))
            self.assertEqual(bundle, original)

    def test_legacy_single_observation_and_plan_only_handoffs(self):
        for observation in (None, self.history[0]):
            with self.subTest(observation=observation), tempfile.TemporaryDirectory() as td:
                output = Path(td) / 'restored'
                report = moves.unpack_handoff(moves.handoff_bundle(self.plan, observation), output)
                expected = [] if observation is None else [observation]
                self.assertEqual(moves.read_json_file(output / 'checkpoints.json'), expected)
                self.assertEqual(report['checkpoint_count'], len(expected))
                self.assertEqual(report['decision'], 'human_review_required' if observation is None else 'stop_and_review')
                self.assertEqual(report['timeline_review'], None if observation is None else moves.review_timeline(self.plan, expected))
                self.assertTrue(report['human_review_required'])
                next_row = {**self.history[-1], 'elapsed_hours': 4, 'active_minutes': 4}
                self.assertEqual(moves.append_checkpoint(self.plan, next_row, expected), [*expected, next_row])

    def test_unstopped_history_still_requires_human_review(self):
        record = {**self.history[1], 'elapsed_hours': 0, 'active_minutes': 0}
        with tempfile.TemporaryDirectory() as td:
            report = moves.unpack_handoff(moves.timeline_handoff(self.plan, [record]), Path(td) / 'new')
            self.assertEqual(report['decision'], 'review_observations')
            self.assertTrue(report['human_review_required'])
            self.assertIsNone(report['first_stop_checkpoint'])

    def test_invalid_bundles_create_no_directory(self):
        bundle = moves.timeline_handoff(self.plan, self.history)
        bad_cases = [None, [], {}, copy.deepcopy(moves.handoff_bundle(self.plan))]
        bad_cases[-1]['plan']['goal'] += ' Edited without rebuilding.'
        for field in ('plan_sha256', 'observations_sha256', 'review', 'card', 'timeline_review'):
            bad = copy.deepcopy(bundle)
            bad[field] = None
            bad_cases.append(bad)
        for mutation in ('drop_stop', 'change_notes', 'change_revision', 'reverse', 'empty'):
            bad = copy.deepcopy(bundle)
            if mutation == 'drop_stop':
                bad['observations'].pop(0)
            elif mutation == 'change_notes':
                bad['observations'][0]['notes'] += ' changed'
            elif mutation == 'change_revision':
                bad['observations'][0]['plan_sha256'] = '0' * 64
            elif mutation == 'reverse':
                bad['observations'].reverse()
            else:
                bad['observations'] = []
            bad_cases.append(bad)
        with tempfile.TemporaryDirectory() as td:
            for index, bad in enumerate(bad_cases):
                with self.subTest(index=index):
                    output = Path(td) / str(index)
                    with self.assertRaises(ValueError):
                        moves.unpack_handoff(bad, output)
                    self.assertFalse(output.exists())

    def test_existing_destinations_and_symlinks_are_never_replaced(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            occupied = root / 'occupied'
            occupied.mkdir()
            sentinel = occupied / 'plan.json'
            sentinel.write_text('keep me', encoding='utf-8')
            empty = root / 'empty'
            empty.mkdir()
            file = root / 'file'
            file.write_text('original', encoding='utf-8')
            for destination in (occupied, empty, file):
                with self.subTest(destination=destination), self.assertRaises(FileExistsError):
                    moves.unpack_handoff(moves.handoff_bundle(self.plan), destination)
            self.assertEqual(sentinel.read_text(), 'keep me')
            self.assertEqual(list(empty.iterdir()), [])
            self.assertEqual(file.read_text(), 'original')
            # Windows runners may not have symlink privileges.
            for name, target in [('link', occupied), ('dangling', root / 'absent')]:
                destination = root / name
                try:
                    destination.symlink_to(target, target_is_directory=True)
                except OSError:
                    continue
                with self.assertRaises(FileExistsError):
                    moves.unpack_handoff(moves.handoff_bundle(self.plan), destination)
                self.assertTrue(destination.is_symlink())
                self.assertFalse((root / 'absent').exists())

    def test_write_failure_cleans_only_its_new_files(self):
        original_open = Path.open
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / 'new'
            def failing_open(path, *args, **kwargs):
                if path == output / 'checkpoints.json':
                    raise OSError('Synthetic disk failure')
                return original_open(path, *args, **kwargs)
            with patch.object(Path, 'open', failing_open), self.assertRaises(OSError):
                moves.unpack_handoff(moves.handoff_bundle(self.plan), output)
            self.assertFalse(output.exists())

    def test_cleanup_preserves_unrelated_file_added_during_failure(self):
        original_open = Path.open
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / 'new'
            def conflicting_open(path, *args, **kwargs):
                if path == output / 'checkpoints.json':
                    with original_open(path, 'x', encoding='utf-8') as handle:
                        handle.write('another writer owns this file')
                return original_open(path, *args, **kwargs)
            with patch.object(Path, 'open', conflicting_open), self.assertRaises(FileExistsError):
                moves.unpack_handoff(moves.handoff_bundle(self.plan), output)
            self.assertEqual(list(output.iterdir()), [output / 'checkpoints.json'])
            self.assertEqual((output / 'checkpoints.json').read_text(), 'another writer owns this file')

    def test_cli_roundtrip_append_export_and_revision_rejection(self):
        bundle = moves.timeline_handoff(self.plan, self.history)
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / 'source.json'
            raw = json.dumps(bundle, indent=2) + '\n'
            source.write_text(raw, encoding='utf-8')
            output = root / 'restored'
            result = self.run_cli('unpack-handoff', source, '--output-dir', output)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['decision'], 'stop_and_review')
            plan, history = output / 'plan.json', output / 'checkpoints.json'
            next_file = root / 'next.json'
            next_file.write_text(json.dumps({**self.history[-1], 'elapsed_hours': 4, 'active_minutes': 4}), encoding='utf-8')
            appended = root / 'appended.json'
            result = self.run_cli('record', plan, next_file, '--history', history, '--output', appended)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(moves.read_json_file(appended)[:3], self.history)
            new_bundle = root / 'new-handoff.json'
            for args in [('handoff', plan, '--timeline', appended, '--output', new_bundle),
                         ('verify-handoff', new_bundle), ('timeline', plan, appended),
                         ('render', plan, '--format', 'html'), ('debrief', plan, appended)]:
                result = self.run_cli(*args)
                self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(moves.read_json_file(new_bundle)['timeline_review']['decision'], 'stop_and_review')
            revised = root / 'revised.json'
            result = self.run_cli('select', plan, '--move-id', 'move-02', '--reason', 'Synthetic revision',
                                  '--first-step', 'Review only', '--output', revised)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = self.run_cli('timeline', revised, history)
            self.assertEqual(result.returncode, 1)
            self.assertIn('current plan revision', result.stderr)
            self.assertEqual(source.read_text(), raw)
            self.assertEqual(self.run_cli('unpack-handoff', source, '--output-dir', output).returncode, 1)

    def test_cli_rejects_bad_json_and_oversize_before_creating_output(self):
        from validate_plan import MAX_PLAN_BYTES
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source, output = root / 'bad.json', root / 'new'
            for raw in ('null', '{"plan": {}, "plan": {}}', '[' * 10000, ' ' * (MAX_PLAN_BYTES + 1)):
                source.write_text(raw, encoding='utf-8')
                result = self.run_cli('unpack-handoff', source, '--output-dir', output)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
