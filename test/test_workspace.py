import copy
import csv
import io
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from importing import apply_import, plan_import
from server import start_background
from storage import Conflict, Store, bulk_tags, initial_workspace, validate


def payload(rows, **kwargs):
    return {"filename": "tasks.json", "content": json.dumps(rows), **kwargs}


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "tasks.sqlite"
        self.store = Store(self.path)
        self.state = initial_workspace()
        self.state["projects"] = [{"id": "work", "name": "Work", "color": "#778866"}]
        self.state = apply_import(payload([
            {"title": "Plan the launch", "tags": ["Planning", "Launch"], "source_key": "launch-1"},
            {"title": "Buy groceries", "tags": ["Personal"]},
            {"title": "Finish the outline", "tags": ["Writing"]},
        ]), self.state)

    def tearDown(self):
        self.temp.cleanup()

    def test_persistence_and_conflicts(self):
        saved = self.store.save(self.state)
        saved["tasks"][0]["notes"] = "<p>Keep <b>rich text</b>.</p>"
        saved = self.store.save(saved)
        self.assertEqual(Store(self.path).read(), saved)
        with self.assertRaises(Conflict):
            self.store.save(self.state)

    def test_legacy_database_preserved_and_backed_up(self):
        old = Path(self.temp.name) / "legacy.sqlite"
        with closing(sqlite3.connect(old)) as db, db:
            db.execute("CREATE TABLE workspace (id INTEGER PRIMARY KEY, value TEXT)")
            db.execute("INSERT INTO workspace VALUES (1,?)", (json.dumps(self.state),))
        migrated = Store(old).read()
        self.assertEqual([t['number'] for t in migrated['tasks']], [1, 2, 3])
        self.assertTrue(migrated['projects'][0]['active'])
        migrated['version'] = self.state['version']
        for task in migrated['tasks']: task.pop('number')
        for project in migrated['projects']: project.pop('active')
        self.assertEqual(migrated, self.state)
        with closing(sqlite3.connect(old.with_name("legacy.before-python.sqlite"))) as db:
            self.assertEqual(json.loads(db.execute("SELECT value FROM workspace").fetchone()[0]), self.state)

    def test_bulk_tags_only_change_selected_and_named_tags(self):
        before = copy.deepcopy(self.state)
        ids = [t["id"] for t in self.state["tasks"][:2]]
        bulk_tags(self.state, ids, ["Planning", "Quarter 4"], "add")
        self.assertEqual(self.state["tasks"][0]["tags"], ["Planning", "Launch", "Quarter 4"])
        self.assertEqual(self.state["tasks"][1]["tags"], ["Personal", "Planning", "Quarter 4"])
        self.assertEqual(self.state["tasks"][2], before["tasks"][2])
        bulk_tags(self.state, ids, ["Planning", "Not present"], "remove")
        self.assertEqual(self.state["tasks"][0]["tags"], ["Launch", "Quarter 4"])
        self.assertEqual(self.state["tasks"][1]["tags"], ["Personal", "Quarter 4"])
        self.assertIn("Planning", self.state["tags"])

    def test_invalid_bulk_selection_is_atomic(self):
        before = self.store.save(self.state)
        with self.assertRaises(ValueError):
            self.store.edit(before["version"], lambda s: bulk_tags(s, [s["tasks"][0]["id"], "missing"], ["New"], "add"))
        self.assertEqual(self.store.read(), before)

    def test_generic_csv_bom_quotes_newlines_and_shared_tags(self):
        content = io.StringIO(newline="")
        writer = csv.DictWriter(content, fieldnames=["title", "tags", "notes", "project", "due", "milestone"])
        writer.writeheader()
        writer.writerow({"title": 'Review "Q4", together', "tags": "Work|Review", "notes": "First line\nSecond line", "project": "Work", "due": "2026-12-10", "milestone": "true"})
        data = {"filename": "tasks.csv", "content": "\ufeff" + content.getvalue(), "defaults": {"tags": "Shared,Work", "status": "doing"}}
        summary, tasks = plan_import(data, self.state)
        self.assertTrue(summary["canImport"])
        self.assertEqual(tasks[0]["tags"], ["Work", "Review", "Shared"])
        self.assertEqual(tasks[0]["project"], "work")
        self.assertEqual(tasks[0]["status"], "doing")
        self.assertTrue(tasks[0]["milestone"])
        self.assertIn("<br>", tasks[0]["notes"])
        self.assertEqual(len(self.state["tasks"]), 3)

    def test_minimal_and_wrapped_json(self):
        for content in ([{"title": "Call a friend"}], {"tasks": [{"title": "Call a friend"}]}):
            summary, tasks = plan_import(payload(content), self.state)
            self.assertEqual(summary["count"], 1)
            self.assertEqual(tasks[0]["tags"], [])
            self.assertEqual(tasks[0]["status"], "backlog")

    def test_duplicates_existing_and_repeated_rows(self):
        data = payload([{"title": "Renamed source", "source_key": "launch-1"}, {"title": "Buy groceries"}, {"title": "New task"}, {"title": "New task"}])
        summary, _ = plan_import(data, self.state)
        self.assertEqual((summary["count"], summary["skipped"]), (1, 3))
        summary, _ = plan_import({**data, "duplicates": "allow"}, self.state)
        self.assertEqual((summary["count"], summary["skipped"]), (4, 0))

    def test_same_title_different_projects_is_distinct(self):
        summary, _ = plan_import(payload([{"title": "Buy groceries", "project": "Work"}]), self.state)
        self.assertEqual(summary["count"], 1)

    def test_optional_paths_and_plain_text_notes(self):
        data = payload([{"title": "A file", "path": "C:\\Work\\Report.pdf", "notes": '<img src=x onerror="alert(1)">'}, {"title": "A different title", "path": "c:/work/report.pdf"}])
        summary, tasks = plan_import(data, self.state)
        self.assertEqual(summary["skipped"], 1)
        self.assertIn("&lt;img", tasks[0]["notes"])
        self.assertIn("File: C:", tasks[0]["notes"])

    def test_preview_rejects_notes_that_expand_beyond_storage_limit(self):
        summary, _ = plan_import(payload([{"title": "Escaped notes", "notes": "<" * 50_000}]), self.state)
        self.assertFalse(summary["canImport"])
        self.assertIn("formatted notes", summary["errors"][0]["error"])

    def test_invalid_rows_block_whole_import(self):
        saved = self.store.save(self.state)
        for row in [{"title": ""}, {"title": "Bad date", "due": "2026-02-30"}, {"title": "Wrong project", "project": "Missing"}, {"title": "Typo", "custom_field": "ignored?"}, {"title": "Bad tags", "tags": [42]}, {"title": "Reversed", "start": "2026-12-31", "due": "2026-01-01"}]:
            with self.subTest(row=row):
                data = payload([{"title": "Valid task"}, row])
                summary, _ = plan_import(data, saved)
                self.assertFalse(summary["canImport"])
                self.assertEqual(summary["errors"][0]["row"], 2)
                with self.assertRaises(ValueError):
                    self.store.edit(saved["version"], lambda s: apply_import(data, s))
                self.assertEqual(self.store.read(), saved)

    def test_bad_headers_json_and_row_limit(self):
        for data in [{"filename": "tasks.csv", "content": "title,title\nOne,Two"}, {"filename": "tasks.csv", "content": "tags\nOne"}, {"filename": "tasks.json", "content": "{"}, payload([]), payload([{"title": str(i)} for i in range(5001)])]:
            with self.subTest(data=str(data)[:100]), self.assertRaises(ValueError):
                plan_import(data, self.state)

    def test_cycles_and_rich_metadata(self):
        a, b = self.state["tasks"][:2]
        a["dependencies"] = [b["id"]]
        b["dependencies"] = [a["id"]]
        with self.assertRaisesRegex(ValueError, "cycle"):
            validate(self.state)
        b["dependencies"] = []
        a.update(reminder="2026-12-01T10:30", milestone=True, checklist=[{"id": "one", "text": "Small step", "done": True}])
        self.store.save(validate(self.state))
        self.assertTrue(self.store.read()["tasks"][0]["milestone"])

    def test_http_import_tags_conflicts_and_origin_protection(self):
        server = start_background(db_path=self.path)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        base = f"http://127.0.0.1:{server.server_address[1]}"

        def call(path, body=None, method=None, **headers):
            req = Request(base + path, data=None if body is None else json.dumps(body).encode(), headers={"Content-Type": "application/json", **headers}, method=method)
            with urlopen(req) as response:
                return json.load(response)

        self.assertEqual(call('/api/health')["runtime"], "python")
        data = payload([{"title": "Imported through HTTP", "tags": ["General"]}])
        preview = call('/api/import/preview', data)
        self.assertEqual(call('/api/workspace')["tasks"], [])
        imported = call('/api/import', {**data, "version": preview["version"]})
        edited = call('/api/tags', {"version": imported["version"], "ids": [imported["tasks"][0]["id"]], "tags": ["Batch"], "mode": "add"})
        self.assertEqual(edited["tasks"][0]["tags"], ["General", "Batch"])
        with self.assertRaises(HTTPError) as conflict:
            call('/api/import', {**data, "version": preview["version"]})
        self.assertEqual(conflict.exception.code, 409)
        with self.assertRaises(HTTPError) as forbidden:
            call('/api/workspace', edited, method="PUT", Origin="https://outside.example")
        self.assertEqual(forbidden.exception.code, 403)
        with self.assertRaises(HTTPError) as private:
            call('/storage.py')
        self.assertEqual(private.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
