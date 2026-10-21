import copy
import json
from pathlib import Path
import tempfile
import unittest

from importing import apply_import
from storage import Store


class DefaultsCancelledTests(unittest.TestCase):
    def test_existing_database_upgrade_preserves_tasks_and_settings(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(Path(folder) / 'tasks.sqlite')
            state = apply_import({'filename': 'tasks.json', 'content': '[{"title":"Existing task","notes":"Keep me"}]'}, store.read())
            state['projects'] = [{'id': 'work', 'name': 'Work', 'color': '#112233', 'active': True}]
            state['tasks'][0]['project'] = 'work'
            state = store.save(state)
            state['columns'] = [c for c in state['columns'] if c['id'] != 'cancelled']
            with store.connect() as db:
                db.execute('UPDATE workspace SET value=? WHERE id=1', (json.dumps(state),))
            upgraded = Store(store.path).read()
            expected = copy.deepcopy(state)
            expected['columns'].append({'id': 'cancelled', 'name': 'Cancelled'})
            expected['version'] += 1
            self.assertEqual(upgraded, expected)
            self.assertEqual(Store(store.path).read(), upgraded)
            snapshots = list(Path(folder).glob('tasks-backups/*.json'))
            self.assertTrue(any(json.loads(p.read_text()) == state for p in snapshots))
            for project in ('work', ''):
                upgraded['settings']['defaultProject'] = project
                upgraded['tasks'][0]['status'] = 'cancelled'
                upgraded = store.save(upgraded)
                self.assertEqual(Store(store.path).read(), upgraded)
                self.assertEqual(upgraded['tasks'][0]['number'], state['tasks'][0]['number'])
            upgraded['tasks'][0]['status'] = 'backlog'
            reopened = store.save(upgraded)
            self.assertEqual(reopened['tasks'], state['tasks'])

    def test_restore_legacy_backup_keeps_cancelled_available(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(Path(folder) / 'tasks.sqlite')
            state = store.read()
            state['columns'] = [c for c in state['columns'] if c['id'] != 'cancelled']
            store._backup(state, force=True)
            backup = store.recovery_list()['backups'][0]['name']
            restored = store.recover({'version': state['version'], 'backup': backup})
            self.assertIn('cancelled', [c['id'] for c in restored['columns']])
