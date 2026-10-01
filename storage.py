"""Local SQLite storage, shared by the desktop app and the standalone Python server."""
from __future__ import annotations

import copy
import json
import os
import re
import sqlite3
from contextlib import closing, contextmanager
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_DB = Path(os.environ.get("DB_PATH", ROOT / "data" / "tasks.sqlite"))
MAX_TASKS = 10_000


class Conflict(ValueError):
    pass


def initial_workspace():
    return {
        "version": 1, "tasks": [], "projects": [], "tags": [],
        "columns": [{"id": key, "name": name} for key, name in
                    [("backlog", "Backlog"), ("next", "Up next"),
                     ("doing", "In progress"), ("done", "Done")]],
        "settings": {"coloring": "priority"},
    }


def text(value, name, limit, *, required=False):
    if not isinstance(value, str) or len(value) > limit or (required and not value.strip()):
        raise ValueError(f"Invalid {name} (maximum {limit} characters)")
    return value


def tags_list(value):
    if not isinstance(value, list) or len(value) > 200:
        raise ValueError("Tags must be a list with at most 200 entries")
    for tag in value:
        text(tag, "tag", 100, required=True)
    return value


def date_value(value, name, *, timestamp=False):
    text(value, name, 50)
    if value:
        try:
            if timestamp:
                datetime.fromisoformat(value.replace("Z", "+00:00"))
            else:
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                    raise ValueError()
                date.fromisoformat(value)
        except ValueError:
            raise ValueError(f"Invalid {name}: {value}") from None
    return value


def validate(state):
    if not isinstance(state, dict) or type(state.get("version")) is not int:
        raise ValueError("Invalid workspace version")
    for name in ("tasks", "columns", "projects", "tags"):
        if not isinstance(state.get(name), list):
            raise ValueError(f"Invalid {name}")
    if len(state["tasks"]) > MAX_TASKS:
        raise ValueError(f"A workspace supports at most {MAX_TASKS:,} tasks")
    for name in ("tasks", "columns", "projects"):
        identifiers = []
        for item in state[name]:
            if not isinstance(item, dict) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,99}", str(item.get("id", ""))):
                raise ValueError(f"Invalid {name} identifier")
            identifiers.append(item["id"])
        if len(set(identifiers)) != len(identifiers):
            raise ValueError(f"Duplicate {name} identifiers")
    columns = {c["id"] for c in state["columns"]}
    projects = {p["id"] for p in state["projects"]}
    if "done" not in columns or len(columns) < 2:
        raise ValueError("Keep the Done column and at least one active column")
    for item in state["columns"] + state["projects"]:
        text(item.get("name"), "name", 100, required=True)
    for project in state["projects"]:
        if type(project.get("active", True)) is not bool:
            raise ValueError("Project active flag must be true or false")
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", str(project.get("color", ""))):
            raise ValueError("Invalid project color")
    for tag in state["tags"]:
        text(tag, "tag", 100, required=True)
    if state.get("settings", {}).get("coloring") not in {"priority", "project", "deadline", "none"}:
        raise ValueError("Invalid color rule")
    zoom = state["settings"].get("zoom", 100)
    if type(zoom) is not int or not 80 <= zoom <= 180 or zoom % 10:
        raise ValueError("Zoom must be 80 to 180 percent in steps of 10")
    tasks = {t["id"]: t for t in state["tasks"]}
    validate_saved_views(state.get("savedViews", []))
    for task in state["tasks"]:
        text(task.get("delegatedTo", ""), "delegated person", 200)
        date_value(task.get("reviewDate", ""), "review date")
        cadence = task.get("reviewEveryDays", 0)
        if type(cadence) is not int or not 0 <= cadence <= 3650:
            raise ValueError("Review cadence must be 0 to 3650 days")
        if type(task.get("onRadar", False)) is not bool:
            raise ValueError("On radar must be true or false")
        parent = task.get("parentId", "")
        if not isinstance(parent, str) or (parent and (parent not in tasks or parent == task["id"] or tasks[parent].get("parentId"))):
            raise ValueError("Subtasks need an existing top-level parent; only one level is supported")
        history = task.get("reviewHistory", [])
        if not isinstance(history, list) or len(history) > 1000:
            raise ValueError("Keep at most 1000 review updates per task")
        for entry in history:
            if not isinstance(entry, dict):
                raise ValueError("Invalid review update")
            date_value(entry.get("at"), "review timestamp", timestamp=True)
            if not entry["at"]:
                raise ValueError("Review update needs a timestamp")
            text(entry.get("note"), "review update", 5000)
        text(task.get("title"), "task title", 500, required=True)
        if task.get("status") not in columns or task.get("project") not in projects | {""}:
            raise ValueError("Invalid task status or project")
        if task.get("priority") not in {"low", "medium", "high", "urgent"}:
            raise ValueError("Invalid task priority")
        tags_list(task.get("tags"))
        deps = task.get("dependencies")
        if not isinstance(deps, list) or any(not isinstance(d, str) or d not in tasks or d == task["id"] for d in deps):
            raise ValueError("Invalid task dependencies")
        if not isinstance(task.get("checklist"), list):
            raise ValueError("Invalid checklist")
        for entry in task["checklist"]:
            if not isinstance(entry, dict) or type(entry.get("done")) is not bool:
                raise ValueError("Invalid checklist entry")
            text(entry.get("text"), "checklist text", 2000)
        text(task.get("notes"), "notes", 200_000)
        date_value(task.get("start"), "start date")
        date_value(task.get("due"), "due date")
        if task["start"] and task["due"] and task["start"] > task["due"]:
            raise ValueError("Due date must be on or after the start date")
        date_value(task.get("reminder"), "reminder", timestamp=True)
        for key in ("completedAt", "remindedAt", "createdAt"):
            date_value(task.get(key, ""), key, timestamp=True)
        if type(task.get("milestone")) is not bool:
            raise ValueError("Milestone must be true or false")
        if "sourceKey" in task:
            text(task["sourceKey"], "source key", 4000)
    # Iterative topological traversal also works for very long dependency chains.
    degrees = {key: len(set(t["dependencies"])) for key, t in tasks.items()}
    children = {key: [] for key in tasks}
    for key, task in tasks.items():
        for parent in set(task["dependencies"]):
            children[parent].append(key)
    ready = [key for key, count in degrees.items() if count == 0]
    visited = 0
    while ready:
        key = ready.pop()
        visited += 1
        for child in children[key]:
            degrees[child] -= 1
            if degrees[child] == 0:
                ready.append(child)
    if visited != len(tasks):
        raise ValueError("Dependencies cannot form a cycle")
    return state


FILTER_OPS = {
    "due": {"overdue", "today", "7", "14", "30", "week", "month", "none"},
    "review": {"due", "7", "14", "30", "none"},
    "delegated": {"yes", "no", "person"},
    "tags": {"any", "all", "none"},
    "status": {"active", "done", "is", "isNot"},
    "project": {"is", "isNot"}, "priority": {"is", "isNot"},
    "blocked": {"yes", "no"}, "radar": {"yes", "no"},
    "parent": {"top", "sub"}, "progress": {"not-started", "partial", "completed"},
}


def validate_filter(node, depth=0):
    if not isinstance(node, dict) or depth > 3:
        raise ValueError("Invalid filter or too many nested groups")
    if "rules" in node:
        if node.get("mode") not in {"all", "any"} or not isinstance(node["rules"], list) or len(node["rules"]) > 20:
            raise ValueError("Filter groups support all/any and at most 20 conditions")
        for rule in node["rules"]:
            validate_filter(rule, depth + 1)
    else:
        ops = node.get("op")
        ops = ops if isinstance(ops, list) else [ops]
        if len(ops) > 20 or any(not isinstance(op, str) or op not in FILTER_OPS.get(node.get("field"), set()) for op in ops):
            raise ValueError("Invalid filter condition")
        values = node.get("value", "")
        values = values if isinstance(values, list) else [values]
        if len(values) > 200:
            raise ValueError("Select at most 200 filter values")
        for value in values:
            text(value, "filter value", 2000)
        if type(node.get("includeOverdue", False)) is not bool:
            raise ValueError("Invalid overdue option")


def validate_saved_views(views):
    if not isinstance(views, list) or len(views) > 100:
        raise ValueError("Keep at most 100 saved views")
    ids = set()
    for view in views:
        if not isinstance(view, dict):
            raise ValueError("Invalid saved view")
        identifier = text(view.get("id"), "view identifier", 99, required=True)
        if not re.fullmatch(r"[a-zA-Z0-9_-]+", identifier) or identifier in ids:
            raise ValueError("Invalid or duplicate view identifier")
        ids.add(identifier)
        text(view.get("name"), "view name", 100, required=True)
        if not isinstance(view.get("filter"), dict) or "rules" not in view["filter"]:
            raise ValueError("A saved filter must have a root condition group")
        validate_filter(view.get("filter"))


class Store:
    def __init__(self, path=DEFAULT_DB):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            existed = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='workspace'").fetchone()
            if existed and db.execute("PRAGMA user_version").fetchone()[0] == 0:
                backup = self.path.with_name(self.path.stem + ".before-python.sqlite")
                if not backup.exists():
                    with closing(sqlite3.connect(backup)) as target:
                        db.backup(target)
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("CREATE TABLE IF NOT EXISTS workspace (id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL)")
            db.execute("INSERT OR IGNORE INTO workspace VALUES (1,?)", (json.dumps(initial_workspace()),))
            db.execute("CREATE TABLE IF NOT EXISTS task_numbers (number INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL UNIQUE)")
            current = json.loads(db.execute("SELECT value FROM workspace WHERE id=1").fetchone()[0])
            before = copy.deepcopy(current)
            self._number_tasks(db, current)
            for project in current["projects"]:
                project.setdefault("active", True)
            if current != before:
                current["version"] += 1
                db.execute("UPDATE workspace SET value=? WHERE id=1", (json.dumps(current, ensure_ascii=False),))
            db.execute("PRAGMA user_version=1")

    @staticmethod
    def _number_tasks(db, state):
        numbers = dict(db.execute("SELECT task_id, number FROM task_numbers"))
        missing = [(t["id"],) for t in state["tasks"] if t["id"] not in numbers]
        if missing:
            db.executemany("INSERT INTO task_numbers(task_id) VALUES (?)", missing)
            numbers = dict(db.execute("SELECT task_id, number FROM task_numbers"))
        for task in state["tasks"]:
            task["number"] = numbers[task["id"]]

    @contextmanager
    def connect(self):
        # Each operation owns its connection; safe for desktop/server threads.
        db = sqlite3.connect(self.path, timeout=15)
        try:
            with db:
                yield db
        finally:
            db.close()

    def read(self):
        with self.connect() as db:
            return json.loads(db.execute("SELECT value FROM workspace WHERE id=1").fetchone()[0])

    def edit(self, expected_version, operation):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            current = json.loads(db.execute("SELECT value FROM workspace WHERE id=1").fetchone()[0])
            if type(expected_version) is not int or expected_version != current["version"]:
                raise Conflict("This workspace changed in another window. Reload or preview again before editing.")
            result = operation(copy.deepcopy(current))
            previous_projects = {p["id"]: p for p in current["projects"]}
            previous_tasks = {t["id"]: t for t in current["tasks"]}
            for project in result["projects"]:
                project.setdefault("active", previous_projects.get(project["id"], {}).get("active", True))
            archived = {p["id"] for p in result["projects"] if p.get("active") is False}
            for task in result["tasks"]:
                if task["project"] in archived and previous_tasks.get(task["id"], {}).get("project") != task["project"]:
                    raise ValueError("Restore the archived project before assigning new tasks to it")
            validate(result)
            self._number_tasks(db, result)
            result["version"] = current["version"] + 1
            db.execute("UPDATE workspace SET value=? WHERE id=1", (json.dumps(result, ensure_ascii=False),))
            return result

    def save(self, state):
        return self.edit(state.get("version"), lambda _: copy.deepcopy(state))


def save_receipt(saved, submitted):
    previous = {t["id"]: t.get("number") for t in submitted["tasks"]}
    return {"version": saved["version"], "numbers": {t["id"]: t["number"] for t in saved["tasks"] if previous.get(t["id"]) != t["number"]}}


def bulk_tags(state, identifiers, tags, mode):
    if mode not in {"add", "remove"}:
        raise ValueError("Choose add or remove")
    if not isinstance(identifiers, list) or not identifiers or any(not isinstance(i, str) for i in identifiers):
        raise ValueError("Select at least one task")
    selected = set(identifiers)
    if not selected <= {t["id"] for t in state["tasks"]}:
        raise ValueError("Some selected tasks no longer exist; select them again")
    tags = list(dict.fromkeys(t.strip() for t in tags_list(tags)))
    if not tags:
        raise ValueError("Choose at least one tag")
    for task in state["tasks"]:
        if task["id"] in selected:
            task["tags"] = (list(dict.fromkeys(task["tags"] + tags)) if mode == "add"
                            else [t for t in task["tags"] if t not in tags])
    if mode == "add":
        state["tags"] = list(dict.fromkeys(state["tags"] + tags))
    return state
