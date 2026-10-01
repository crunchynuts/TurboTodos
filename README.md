# TurboTodos — desktop edition

A local task workspace with board, grid, timeline, rich notes, reminders, and a receipt-style done stack. Python and SQLite handle persistence. The interface runs in its own desktop window using pywebview, with no localhost server or browser tab in desktop mode. No Node.js, npm, or frontend build is needed.

## Run

Python 3.12 is tested. On Windows, Microsoft Edge WebView2 Runtime and .NET Framework 4.6.2 or later are required (normally already installed). Install WebView2 from Microsoft if the app reports it missing. The UI uses embedded HTML/CSS/JavaScript; Python runs the application and talks directly to SQLite.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

Double-click `app.py` or run it in your editor. The launcher automatically uses the project’s `.venv` when present, even if Windows associates `.py` files with a different Python installation. Startup failures show a Windows error dialog and write `startup-error.log` beside the launcher. Without a `.venv`, the selected Python must have the requirements installed. Closing the window exits the app. Reminders appear inside the app while it is open. Excel exports and CSV templates use a native Save As dialog.

To move to another computer, copy or zip the project without `.venv` and `__pycache__`, then install requirements there. Include `data` to carry over your tasks, or omit it for a fresh workspace. Do not copy a running database; close the app first. Use `python app.py --db path/to/tasks.sqlite` for a different database.

Optional browser mode remains available through `python server.py --port 3000`, then http://localhost:3000. It uses the same SQLite database and requires only Python's standard library. Desktop mode does not start or import that server.

## Bulk tags

1. Click **Select tasks**. Square selection checkboxes appear in every view, separate from the round completion buttons.
2. Select individual tasks, or filter first and click **Select all N filtered**.
3. Choose **Add tags** or **Remove tags**. Enter comma-separated tags or click suggestions.

Adding merges tags without duplicates. Removing changes only the named tags on selected tasks; other tags and the global tag list stay intact. Selection persists across filters, and the selection bar explicitly counts hidden selected tasks. **Clear selection** resets it. Bulk edits support the same one-level undo as other workspace changes.

## Generic task imports

Click **Import tasks**, choose a UTF-8 `.csv` / `.json` file or paste a list, add optional shared tags/defaults, then **Preview import**. Only `title` is required. The importer works for any task list; file tracking is just one possible use.

```csv
title,tags,priority,notes
Plan the next release,"Planning,Launch",high,Agree on the next steps.
Book a haircut,Personal,low,
```

```json
[
  {"title": "Plan the next release", "tags": ["Planning", "Launch"]},
  {"title": "Book a haircut", "tags": ["Personal"]}
]
```

JSON also accepts `{"tasks": [...]}`. Download a CSV template in the import dialog.

| Field | Meaning |
| --- | --- |
| `title` | Required, up to 500 characters. `name` and `filename` are accepted aliases. |
| `tags` | Comma/pipe-separated string or JSON list. Merged with shared import tags. |
| `project` | Existing project name or ID; nonblank values override the default. |
| `status` | Existing column name or ID; nonblank values override the default. |
| `priority` | low / medium (default) / high / urgent. |
| `start`, `due` | YYYY-MM-DD. |
| `notes` | Plain text; line breaks preserved and HTML treated as text. |
| `milestone` | true / false (also yes/no or 1/0). |
| `reminder` | YYYY-MM-DDTHH:MM, local time. |
| `source_key` | Optional stable identifier from any source for repeat-import deduplication. |
| `path` | Optional convenience field added to notes; also used as source_key when blank. Referenced files are never opened or uploaded. |

Imports create new tasks and never update existing tasks. By default, duplicates are skipped against both existing tasks and earlier rows in the file. Matching uses source_key when supplied, otherwise case-insensitive title + project. You can explicitly allow duplicates. Keep using the same source keys across repeat imports.

Invalid dates, unknown columns/projects/statuses, and missing titles block the entire import with row numbers. Nothing is partially imported. Changing any input invalidates the preview; a concurrent workspace change also requires a new preview. Limits: **5,000 tasks / 8 MB per import**, **10,000 tasks per workspace**. The preview table shows the first 100 rows, but every row is validated. Imports support one-level undo.

### Optional folder-listing example

The importer is generic. This helper is just one producer of the standard task rows:

```powershell
python tools/catalogue_files.py "C:\Work\Documents" --recursive --tag Catalogue --tag Review --output tasks.csv
```

It lists filenames/paths without opening file contents. Choose a .json output for JSON instead. It refuses to overwrite existing output files.

## Storage and migration

Data lives in `data/tasks.sqlite` with SQLite WAL journaling. The earlier app's database is read directly: existing tasks, notes, reminders, dependencies, tags, and columns are retained. On first opening an older database, Python creates a consistent backup at `data/tasks.before-python.sqlite`.

For manual backup, stop all TurboTodos processes and copy the data folder. Set `DB_PATH` to choose another database, or use `python server.py --db path/to/tasks.sqlite`. Data, caches, and .venv are excluded from Git.

Desktop mode opens no listening port. Optional browser mode binds only to loopback. There is no cloud service.

## Existing features

- Custom columns and immediate pointer dragging; group by status, project, priority, or tag.
- Grid with inline edits; timeline with date ranges, dependencies, and milestones.
- Filters, search, sorting, and color rules by priority/project/deadline.
- Rich notes, checklists, duplication, and dependency-cycle validation.
- Real Excel export of filtered tasks, including notes and checklists.
- In-app reminders while open; missed reminders on next launch; optional browser notifications in browser mode.
- Completed task receipts with reopening; one-level undo.

| Shortcut | Action |
| --- | --- |
| N | New task |
| / | Search |
| 1 / 2 / 3 | Board / Grid / Timeline |
| Ctrl/Cmd + Enter | Save task details |
| Ctrl/Cmd + Z | Undo last workspace change (outside a text editor) |
| Esc | Close panel |
| ? | Shortcut reference |

Task details save explicitly; grid and board changes save immediately. Failed saves remain visible. Concurrent edits are rejected rather than overwriting another window; reopen the window to get its latest state, copying any unsaved edits first. Timeline bars open the date editor. Dependencies indicate waiting tasks without automatically rescheduling them.

## Test

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s test -v
```

Tests use temporary databases and cover migration/backups, persistence, conflicts, atomic bulk edits/imports, generic CSV/JSON, validation, duplicate handling, HTTP routes, the desktop bridge, and native export handling.

## Reviews, delegation, subtasks, and saved filters

Task details include **Delegated to**, **Next review**, **Review every (days)**, and **Keep on Radar**. These are optional built-in fields. Review cadence is a day interval (14 means fortnightly; 0 means no repeat). Click **Reviewed / add update** to record a timestamped note and choose the next review; the default is today plus the cadence. This never changes the deadline or completes the task. Leave the next review blank to stop scheduling it.

**Radar** gathers incomplete tasks explicitly kept on Radar, tasks with review dates, delegated tasks, and deadlines within 30 days (including overdue). It sorts by review date, then deadline. **My day** shows overdue/today deadlines, reviews due, and active In progress work without delegation or future review tracking. **Delegated** gathers incomplete work with an owner.

Create one-level **subtasks** from a saved parent's details, or choose a parent in a task's details. Each subtask has independent dates, tags, notes, ownership, reviews and dependencies. Parent cards show completion counts and expand/collapse children within the same group; children in other status groups stay visible there. Filters always surface matching subtasks, with parent context, even when collapsed. All children complete means **Ready to complete**; parents never close automatically. Completing a parent with open children asks for confirmation. Deleting a parent keeps its children as top-level tasks. Duplicating a parent copies only that task, not its children or review history. Checklists remain lightweight steps.

**Advanced filters** support nested all/any groups, dates, delegation, any/all/none tags, status, project, priority, blocked dependencies, Radar flags, and task level. Date presets cover overdue, today, 7/14/30 days, this Monday–Sunday week, and this calendar month. A rolling 7-day window includes today plus six days. Future windows exclude overdue unless **Include overdue** is checked. The Show done checkbox controls completed-task visibility; date choices combine with the other filters. The Done stack always shows completed tasks.

Save named advanced filters from the filter editor; they appear in the sidebar and persist in SQLite. Saving captures the advanced condition tree, not the separate basic filters or current view layout. Loading a saved view clears basic filters and starts from All tasks. Relative dates are recalculated when the view renders. Use nested groups for **Incomplete AND (Overdue OR Review due)**.

Generic imports additionally accept `delegated_to`, `review_date` (YYYY-MM-DD), `review_every_days` (0–3650), `on_radar` (true/false), and `parent_id` (an existing top-level task ID). Excel export includes task/parent IDs, delegation, review settings and review history. Existing databases need no destructive migration; absent new fields are treated as empty/default values.

The optional Windows runtime smoke test uses a temporary database and the real embedded engine:

```powershell
.\.venv\Scripts\python.exe test/desktop_smoke.py
```

## Performance checks

Workspace rendering reuses unchanged task cards, grid rows, controls, and scroll containers. Task/parent/project indexes avoid repeated full-list scans; note excerpts and date formatters are cached. Off-screen board cards defer layout work. Saves remain ordered, version-checked, and asynchronous; desktop requests avoid an extra JSON encode/decode round trip. Undo and explicit detail saves retain their existing behavior.

Run the synthetic desktop benchmark (temporary database; no changes to personal tasks):

```powershell
.\.venv\Scripts\python.exe test/desktop_benchmark.py 500
.\.venv\Scripts\python.exe test/desktop_benchmark.py 1000
```

Numbers are milliseconds for JavaScript plus forced layout, not database round-trip time. Each action reports its first sample and median of five samples. The harness disables persistence for those rendering measurements; `desktop_smoke.py` separately verifies real saves, review history, exports, inline editing, bulk selection and undo. First-time creation of a large grid is more expensive than updating its existing rows.

## Multi-select filters and Help

Basic Tags, Priority, Status, and Projects filters use checkbox menus: select multiple choices without Ctrl. Sidebar tags also toggle independently. Quick date filters combine selected windows with OR and preserve other filter selections. Advanced filters support multiple values for projects, statuses, priorities, people, and tags, plus multiple date/review/state choices. Values within one condition match any selection, except explicit tag all/none and exclusion rules. Separate basic filters combine with AND. Empty choices remove that restriction. Older single-value saved views continue to load. Sort, grouping, and coloring remain display settings.

Open **Help & shortcuts** from the sidebar or the top-bar question mark, or press **?** / **F1**. It includes keyboard shortcuts and guidance for filtering, bulk actions, reviews, and subtasks. Opening Help from a task keeps unsaved edits intact when you close Help.

## Faster task entry, archived projects, and task numbers

New and existing task details show Status, Priority, Project, and Tags as visible selectable chips. Status/Priority/Project allow one choice; Tags allow several. Project names and tags are sorted alphabetically. The New tags box still supports creating tags while saving a task.

Use **Manage projects** below the project list to Archive or Restore a project. The backend stores an `active` boolean; existing projects default to active. Archiving keeps every task and its project association. Archived projects are excluded from new assignment choices and import defaults; the backend also blocks new assignments. Existing tasks can retain their archived project when edited, or move to an active project. Filters still include archived projects so their tasks remain findable.

Every task receives a stable **#number** from SQLite, including existing tasks and imported tasks. Numbers appear in the board, grid, timeline labels, task details, receipts, dependency choices, and Excel export. Search accepts numbers such as `#12`. Numbers do not change on editing or reordering, are not reused after deletion, and survive undo/restoration of the same task. IDs remain the underlying relationship keys. Number allocation is transactional with saving.

## Always-visible task filters

The task header has a View stack button alongside the other actions; the progress banner has been removed. The standalone Filters section shows all quick date choices, tags, projects, priorities, and statuses as selectable chips. Tags and projects are alphabetical, and multiple selections are supported. Different filter categories combine with AND; choices within a category combine with OR. Show done is enabled initially to preserve the complete All tasks view; uncheck it to hide completed tasks. Reset filters clears selections and shows completed tasks again. The Done stack remains dedicated to completed tasks.

Progress filters: Not started / Partial / Completed can be selected independently or together. For a parent, all subtasks Done means Completed; at least one subtask Done or In progress means Partial; otherwise Not started. For an individual task, Done means Completed, In progress means Partial, and other columns mean Not started. This measures progress without changing parent status. Sort uses a single-choice segmented control. Demo tags and projects are prefixed with `Demo: ` for identification.

## Zoom

Use the top-bar minus / percentage / plus controls to scale the entire app from 80% to 180%, in 10% increments. Clicking the percentage resets to 100%. Keyboard shortcuts: Ctrl/Cmd + plus or minus, and Ctrl/Cmd + 0 to reset. Zoom is saved with the workspace and applies to task editors and dialogs without discarding drafts.
