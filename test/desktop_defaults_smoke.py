"""Exercise default-project and cancellation controls against a temporary database."""
import json
from pathlib import Path
import sys
import tempfile
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import webview
from desktop import DesktopAPI, build_html
from storage import Store

folder = tempfile.TemporaryDirectory()
path = Path(folder.name) / 'tasks.sqlite'
store = Store(path)
state = store.read()
state['projects'] = [{'id': 'work', 'name': 'Work', 'color': '#112233', 'active': True}]
store.save(state)
api = DesktopAPI(path)
html = build_html().replace('window.turboHasUnsavedChanges=', 'window.smoke={qol,power,openTask,closeOverlay,render,getState:()=>state};window.turboHasUnsavedChanges=')
window = webview.create_window('Default project validation', html=html, js_api=api, hidden=True)
api._window = window
results = []


def js(code):
    return window.evaluate_js('(()=>{const check=(v,m)=>{if(!v)throw Error(m)};' + code + '})()')


def flush():
    for _ in range(200):
        if not window.evaluate_js('turboHasUnsavedChanges()'):
            return
        time.sleep(.05)
    raise AssertionError('Save did not finish')


def run():
    try:
        for _ in range(100):
            if window.evaluate_js('Boolean(window.smoke)'):
                break
            time.sleep(.1)
        results.append(js('''
          smoke.openTask(null);
          document.querySelector('#task-title').value='Default task';
          document.querySelector('[name=project][value=work]').checked=true;
          document.querySelector('[name=defaultProject]').checked=true;
          document.querySelector('#task-form').requestSubmit();
          check(smoke.getState().settings.defaultProject==='work','Default saved');
          smoke.openTask(null);
          check(document.querySelector('[name=project]:checked').value==='work','Default selected');
          smoke.closeOverlay(true);
          smoke.qol.capture();
          document.querySelector('#capture-title').value='Captured task';
          document.querySelector('#modal-form').requestSubmit();
          check(smoke.getState().tasks.at(-1).project==='work','Capture uses default');
          smoke.closeOverlay(true);
          const s=smoke.getState();
          s.projects[0].active=false;
          check(smoke.power.defaultProject()==='','Archived default falls back');
          s.projects[0].active=true;
          smoke.openTask(null,{project:''});
          check(document.querySelector('[name=project]:checked').value==='','Explicit No project overrides default');
          smoke.closeOverlay(true);
          return 'Default project and Quick capture passed';
        '''))
        flush()
        results.append(js('''
          const t=smoke.getState().tasks[0];
          smoke.openTask(t.id);
          check(!document.querySelector('[name=defaultProject]'),'Existing task has no default control');
          document.querySelector('[name=status][value=cancelled]').checked=true;
          document.querySelector('[name=due]').value='2020-01-01';
          document.querySelector('#task-form').requestSubmit();
          const cancelled=smoke.getState().tasks[0];
          check(cancelled.status==='cancelled'&&!cancelled.completedAt,'Cancelled without completion');
          check(!smoke.power.attention(cancelled).length&&!smoke.power.myDay(cancelled)&&!smoke.power.radar(cancelled),'No active alerts');
          smoke.openTask(null);
          document.querySelector('#task-title').value='No project default';
          document.querySelector('[name=project][value=""]').checked=true;
          document.querySelector('[name=defaultProject]').checked=true;
          document.querySelector('#task-form').requestSubmit();
          smoke.openTask(null);
          check(document.querySelector('[name=project]:checked').value==='','No project default selected');
          smoke.closeOverlay(true);
          check(smoke.power.defaultProject('work')==='','No project default overrides sidebar project');
          return 'Cancellation and No project default passed';
        '''))
        flush()
        saved = Store(path).read()
        assert saved['settings']['defaultProject'] == ''
        assert saved['tasks'][0]['status'] == 'cancelled'
        assert len(saved['tasks']) == 3
        results.append('SQLite persistence after restart passed')
    except Exception as exc:
        results.append('FAILED: ' + str(exc))
    finally:
        print(json.dumps(results), flush=True)
        window.destroy()


webview.start(run, gui='edgechromium', http_server=False)
folder.cleanup()
if any('FAILED' in result for result in results):
    raise SystemExit(1)
