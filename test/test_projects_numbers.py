import copy
import json
from pathlib import Path
import tempfile
import unittest

from importing import apply_import, plan_import
from storage import Store, save_receipt


class ProjectsNumbersTests(unittest.TestCase):
    def test_numbers_are_stable_never_reused_and_survive_undo(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(Path(folder) / 'tasks.sqlite')
            payload = {'filename': 'tasks.json', 'content': json.dumps([{'title': 'One'}, {'title': 'Two'}])}
            state = store.save(apply_import(payload, store.read()))
            self.assertEqual([t['number'] for t in state['tasks']], [1, 2])
            removed = copy.deepcopy(state['tasks'].pop(0))
            state = store.save(state)
            state = store.save(apply_import({'filename': 'tasks.json', 'content': '[{"title":"Three"}]'}, state))
            self.assertEqual([t['number'] for t in state['tasks']], [2, 3])
            state['tasks'].append(removed)
            state['tasks'][0]['number'] = 999
            submitted = copy.deepcopy(state)
            state = store.save(state)
            self.assertEqual([t['number'] for t in state['tasks']], [2, 3, 1])
            self.assertEqual(save_receipt(state, submitted)['numbers'], {state['tasks'][0]['id']: 2})
            self.assertEqual(Store(store.path).read(), state)

    def test_archiving_preserves_tasks_and_blocks_new_assignments(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(Path(folder) / 'tasks.sqlite')
            state = store.read()
            state['projects'] = [{'id': 'work', 'name': 'Work', 'color': '#778866'}]
            payload = {'filename': 'tasks.json', 'content': '[{"title":"One","project":"work"}]'}
            state = store.save(apply_import(payload, state))
            state['projects'][0]['active'] = False
            state = store.save(state)
            self.assertEqual(state['tasks'][0]['project'], 'work')
            state['tasks'][0]['title'] = 'Still editable'
            state = store.save(state)
            self.assertFalse(plan_import(payload, state)[0]['canImport'])
            invalid = copy.deepcopy(state)
            new = copy.deepcopy(invalid['tasks'][0]); new['id'] = 'new-task'
            invalid['tasks'].append(new)
            with self.assertRaises(ValueError): store.save(invalid)
            self.assertEqual(store.read(), state)
            state['projects'][0]['active'] = True
            state = store.save(state)
            self.assertTrue(plan_import(payload, state)[0]['canImport'])
