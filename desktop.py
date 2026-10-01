"""In-memory desktop UI with a direct SQLite bridge; no HTTP listener."""
import base64
import json
from pathlib import Path
import re
from importing import apply_import, plan_import
from storage import ROOT, Conflict, Store, bulk_tags, save_receipt


class DesktopAPI:
    def __init__(self, db_path):
        self._store = Store(db_path)
        self._window = None

    def request(self, method, path, payload=None):
        try:
            if method == "GET" and path == "/api/workspace":
                result = self._store.read()
            else:
                if not isinstance(payload, dict):
                    raise ValueError("Send a JSON object")
                if len(json.dumps(payload).encode()) > 16 * 1024 * 1024:
                    raise ValueError("Request exceeds 16 MB")
                if method == "PUT" and path == "/api/workspace":
                    result = save_receipt(self._store.save(payload), payload)
                elif method == "POST" and path == "/api/import/preview":
                    result, _ = plan_import(payload, self._store.read())
                elif method == "POST" and path == "/api/import":
                    result = self._store.edit(payload.get("version"), lambda s: apply_import(payload, s))
                elif method == "POST" and path == "/api/tags":
                    result = self._store.edit(payload.get("version"), lambda s: bulk_tags(s, payload.get("ids"), payload.get("tags"), payload.get("mode")))
                else:
                    return {"status": 404, "body": {"error": "Not found"}}
            return {"status": 200, "body": result}
        except Conflict as exc:
            return {"status": 409, "body": {"error": str(exc)}}
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            return {"status": 400, "body": {"error": str(exc)}}

    def save_file(self, filename, content):
        import webview
        filename = Path(filename).name
        suffix = Path(filename).suffix.lower()
        if suffix not in {".xlsx", ".csv"} or len(content) > 256 * 1024 * 1024:
            raise ValueError("Unsupported export")
        data = base64.b64decode(content, validate=True)
        paths = self._window.create_file_dialog(webview.FileDialog.SAVE, save_filename=filename,
                                               file_types=(f"Export (*{suffix})",))
        if not paths:
            return False
        target = Path(paths[0])
        if not target.suffix:
            target = target.with_suffix(suffix)
        target.write_bytes(data)
        return True


def build_html():
    public = ROOT / "public"
    def source(name):
        text = (public / name).read_text(encoding="utf-8")
        text = re.sub(r"^import .*?;\s*$", "", text, flags=re.MULTILINE)
        return re.sub(r"\bexport (?=(?:async )?function|const|let)", "", text)

    script = "window.TURBO_DESKTOP=true;\n"
    script += "window.TURBO_IMPORT_TEMPLATE=" + json.dumps((public / "import-template.csv").read_text(encoding="utf-8")) + ";\n"
    script += "(async()=>{\n"
    for name, exports in [("filters.js", "multiSelect,multiValues,inlineChoices"), ("render.js", "patchHTML,renderFragment"), ("transport.js", "apiFetch,saveDownload,preferences"), ("export.js", "exportExcel"), ("bulk.js", "bulk"), ("power.js", "power,matchesFilter,taskProgress")]:
        script += f"const {{{exports}}}=(()=>{{\n{source(name)}\nreturn {{{exports}}};\n}})();\n"
    script += source("app.js") + "\n})();"
    favicon = "data:image/svg+xml;base64," + base64.b64encode((public / "favicon.svg").read_bytes()).decode()
    script = script.replace('src="/favicon.svg"', f'src="{favicon}"').replace('href="/"', 'href="#"')
    html = (public / "index.html").read_text(encoding="utf-8")
    for name in ("style.css", "bulk.css", "power.css"):
        html = html.replace(f'<link rel="stylesheet" href="/{name}">', "<style>" + (public / name).read_text(encoding="utf-8") + "</style>")
    html = html.replace('href="/favicon.svg"', f'href="{favicon}"')
    return html.replace('<script type="module" src="/app.js"></script>', "<script>" + script.replace("</script", "<\\/script") + "</script>")
