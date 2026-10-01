"""CSV/JSON manifest imports. A preview never writes files or changes tasks."""
from __future__ import annotations

import csv
import html
import io
import json
import re
import uuid
from datetime import datetime, timezone

from storage import MAX_TASKS, date_value, tags_list, text

MAX_ROWS = 5000
MAX_FILE_BYTES = 8 * 1024 * 1024
FIELDS = {"title", "filename", "name", "tags", "project", "status", "priority",
          "start", "due", "notes", "path", "source_key", "milestone", "reminder",
          "delegated_to", "review_date", "review_every_days", "on_radar", "parent_id"}


def parse_tags(value):
    if value is None or value == "":
        return []
    if isinstance(value, str):
        value = re.split(r"[,|]", value)
    if not isinstance(value, list) or any(not isinstance(t, str) for t in value):
        raise ValueError("Tags must be a string or a list of strings")
    return list(dict.fromkeys(tags_list([t.strip() for t in value if t.strip()])))


def read_rows(filename, content):
    if not isinstance(content, str) or len(content.encode("utf-8")) > MAX_FILE_BYTES:
        raise ValueError("Choose a UTF-8 CSV or JSON file smaller than 8 MB")
    content = content.lstrip("\ufeff")
    if filename.lower().endswith(".json"):
        try:
            rows = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON at line {exc.lineno}: {exc.msg}") from None
        if isinstance(rows, dict) and set(rows) == {"tasks"}:
            rows = rows["tasks"]
        if not isinstance(rows, list):
            raise ValueError('JSON must be an array of tasks or {"tasks": [...]}')
    elif filename.lower().endswith(".csv"):
        csv.field_size_limit(300_000)
        reader = csv.DictReader(io.StringIO(content, newline=""), strict=True)
        if not reader.fieldnames:
            raise ValueError("CSV needs a header row with a title column")
        headers = [h.strip().lower() for h in reader.fieldnames]
        if len(headers) != len(set(headers)):
            raise ValueError("CSV has duplicate column headers")
        if not {"title", "filename", "name"}.intersection(headers):
            raise ValueError("CSV needs a title column (filename or name also works)")
        reader.fieldnames = headers
        try:
            rows = []
            for row in reader:
                if len(rows) >= MAX_ROWS:
                    raise ValueError(f"Import at most {MAX_ROWS:,} rows at a time")
                if any(value not in (None, "") for value in row.values()):
                    rows.append(row)
        except csv.Error as exc:
            raise ValueError(f"Invalid CSV near line {reader.line_num}: {exc}") from None
    else:
        raise ValueError("Choose a .csv or .json manifest")
    if not rows:
        raise ValueError("The manifest contains no tasks")
    if len(rows) > MAX_ROWS:
        raise ValueError(f"Import at most {MAX_ROWS:,} rows at a time")
    return rows


def resolve(value, collection, label, *, allow_empty=False):
    if not value and allow_empty:
        return ""
    text(value, label, 100, required=True)
    matches = [item["id"] for item in collection if item["id"] == value]
    if not matches:
        matches = [item["id"] for item in collection if item["name"].casefold() == value.casefold()]
    if len(matches) != 1:
        raise ValueError(f"Unknown or ambiguous {label}: {value}. Create it first or use its ID.")
    return matches[0]


def source_key(value):
    # Windows paths are case-insensitive; POSIX paths and arbitrary IDs are not.
    value = value.strip()
    return value.replace("\\", "/").casefold() if re.match(r"^[a-zA-Z]:[\\/]", value) or value.startswith("\\\\") else value


def key_for(task):
    if task.get("sourceKey"):
        return ("source", source_key(task["sourceKey"]))
    return ("title", task["title"].casefold().strip(), task["project"])


def normalize(row, defaults, state):
    if not isinstance(row, dict) or any(not isinstance(key, str) for key in row):
        raise ValueError("Each row must be an object with named columns; check CSV quoting")
    unknown = set(row) - FIELDS
    if unknown:
        raise ValueError("Unknown columns: " + ", ".join(sorted(unknown)))
    if any(value is None for value in row.values()):
        # JSON null optional values and short CSV rows both mean blank.
        row = {key: "" if value is None else value for key, value in row.items()}
    title = row.get("title") or row.get("filename") or row.get("name") or ""
    title = text(title, "title", 500, required=True).strip()
    path = text(row.get("path", ""), "path", 4000).strip()
    source = text(row.get("source_key") or path, "source key", 4000).strip()
    notes = text(row.get("notes", ""), "notes", 180_000)
    if path:
        notes = f"{notes}\n\nFile: {path}".strip()
    notes_html = "<p>" + html.escape(notes).replace("\n", "<br>") + "</p>" if notes else ""
    text(notes_html, "formatted notes", 200_000)
    now = datetime.now(timezone.utc).isoformat()
    first_column = next(c["id"] for c in state["columns"] if c["id"] != "done")
    status = resolve(row.get("status") or defaults.get("status") or first_column, state["columns"], "status")
    project = resolve(row.get("project") or defaults.get("project") or "", [p for p in state["projects"] if p.get("active", True)], "project", allow_empty=True)
    priority = text(row.get("priority") or "medium", "priority", 20).lower()
    if priority not in {"low", "medium", "high", "urgent"}:
        raise ValueError("Priority must be low, medium, high, or urgent")
    start, due = date_value(row.get("start", ""), "start date"), date_value(row.get("due", ""), "due date")
    if start and due and start > due:
        raise ValueError("Due date must be on or after start date")
    milestone = str(row.get("milestone", "")).lower().strip()
    if milestone not in {"", "true", "false", "yes", "no", "1", "0"}:
        raise ValueError("Milestone must be true or false")
    cadence = str(row.get("review_every_days") or "0")
    if not cadence.isdigit() or not 0 <= int(cadence) <= 3650:
        raise ValueError("review_every_days must be an integer from 0 to 3650")
    radar = str(row.get("on_radar", "")).lower().strip()
    if radar not in {"", "true", "false", "yes", "no", "1", "0"}:
        raise ValueError("on_radar must be true or false")
    parent_id = text(row.get("parent_id", ""), "parent ID", 99)
    if parent_id and not any(t["id"] == parent_id and not t.get("parentId") for t in state["tasks"]):
        raise ValueError("parent_id must identify an existing top-level task")
    return {
        "delegatedTo": text(row.get("delegated_to", ""), "delegated person", 200).strip(),
        "reviewDate": date_value(row.get("review_date", ""), "review date"),
        "reviewEveryDays": int(cadence), "onRadar": radar in {"true", "yes", "1"},
        "parentId": parent_id, "reviewHistory": [],
        "id": str(uuid.uuid4()), "title": title, "project": project, "status": status,
        "priority": priority, "tags": parse_tags(parse_tags(row.get("tags")) + parse_tags(defaults.get("tags"))),
        "start": start, "due": due, "notes": notes_html,
        "dependencies": [], "checklist": [], "reminder": date_value(row.get("reminder", ""), "reminder", timestamp=True),
        "remindedAt": "", "milestone": milestone in {"true", "yes", "1"},
        "completedAt": now if status == "done" else "", "createdAt": now, "sourceKey": source,
    }


def plan_import(payload, state):
    if not isinstance(payload, dict) or not isinstance(payload.get("filename"), str):
        raise ValueError("Choose an import file")
    defaults = payload.get("defaults", {})
    if not isinstance(defaults, dict):
        raise ValueError("Invalid import defaults")
    parse_tags(defaults.get("tags"))
    policy = payload.get("duplicates", "skip")
    if policy not in {"skip", "allow"}:
        raise ValueError("Choose skip or allow for duplicates")
    rows = read_rows(payload["filename"], payload.get("content"))
    seen = {key_for(t) for t in state["tasks"]}
    pending, preview, errors = [], [], []
    skipped = 0
    for number, row in enumerate(rows, 1):
        try:
            task = normalize(row, defaults, state)
            key = key_for(task)
            duplicate = key in seen and policy == "skip"
            if duplicate:
                skipped += 1
            else:
                pending.append(task)
                seen.add(key)
            preview.append({"row": number, "title": task["title"], "tags": task["tags"],
                            "project": task["project"], "status": task["status"],
                            "result": "Skip duplicate" if duplicate else "Import"})
        except (ValueError, TypeError) as exc:
            errors.append({"row": number, "error": str(exc)})
            preview.append({"row": number, "title": str(row.get("title", ""))[:100] if isinstance(row, dict) else "",
                            "tags": [], "result": "Error", "error": str(exc)})
    if len(state["tasks"]) + len(pending) > MAX_TASKS:
        errors.append({"row": 0, "error": f"This import exceeds the {MAX_TASKS:,}-task workspace limit"})
    summary = {"version": state["version"], "total": len(rows), "count": len(pending), "skipped": skipped,
               "errors": errors, "preview": preview[:100], "canImport": bool(pending) and not errors}
    return summary, pending


def apply_import(payload, state):
    summary, tasks = plan_import(payload, state)
    if summary["errors"]:
        first = summary["errors"][0]
        raise ValueError(f"Nothing imported. Row {first['row']}: {first['error']}")
    if not tasks:
        raise ValueError("Nothing to import; all rows are duplicates")
    state["tasks"].extend(tasks)
    state["tags"] = list(dict.fromkeys(state["tags"] + [tag for t in tasks for tag in t["tags"]]))
    return state
