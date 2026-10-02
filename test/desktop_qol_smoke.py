"""Temporary-database native runtime checks for productivity workflows."""
import json
from pathlib import Path
import sys
import tempfile
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import webview
from desktop import DesktopAPI, build_html
from importing import apply_import
from storage import Store

folder=tempfile.TemporaryDirectory()
path=Path(folder.name)/'test.sqlite'
store=Store(path)
s=store.save(apply_import({'filename':'tasks.json','content':'[{"title":"Course","start":"2026-10-02","due":"2027-01-02"},{"title":"Alex","start":"2026-10-02","due":"2027-01-02"}]'},store.read()))
s['tasks'][1]['parentId']=s['tasks'][0]['id']
s['tasks'][0]['dependencies']=[s['tasks'][1]['id']]
store.save(s)
api=DesktopAPI(path)
html=build_html().replace('window.turboHasUnsavedChanges=', 'window.smoke={sortTasks,qol,power,bulk,openTask,render,restoreLayout,closeOverlay,filtered,complete,getState:()=>state,ready:()=>saveQueue};window.turboHasUnsavedChanges=')
window=webview.create_window('TurboTodos productivity validation',html=html,js_api=api,hidden=True)
api._window=window
results=[]
def js(code):return window.evaluate_js('(()=>{const check=(v,m)=>{if(!v)throw Error(m)};'+code+'})()')
def flush():
    for _ in range(200):
        if not window.evaluate_js('turboHasUnsavedChanges()'):return
        time.sleep(.05)
    raise AssertionError('Changes did not finish saving')
def run():
    try:
        for _ in range(100):
            if window.evaluate_js('Boolean(window.smoke)'):break
            time.sleep(.1)
        else:raise AssertionError('UI failed to load')
        results.append(js('''
          const s=smoke.getState();
          document.querySelector('[data-action=view][data-value=grid]').click();
          check(document.querySelectorAll('.task-row').length===1,'Grid subtasks start collapsed');
          check(!document.querySelector('.task-row .qol-meta'),'Grid metadata starts collapsed');
          document.querySelector('[data-action=grid-details]').click();
          check(document.querySelector('.task-row .qol-meta').textContent.includes('Blocked by'),'Expand shows dependency links');
          document.querySelector('.task-row [data-power=expand]').click();check(document.querySelectorAll('.task-row').length===2,'Subtasks expand');
          document.querySelector('.task-row [data-power=expand]').click();check(document.querySelectorAll('.task-row').length===1,'Subtasks collapse');
          document.querySelector('[data-action=grid-details]').click();check(!document.querySelector('.task-row .qol-meta'),'Metadata collapses');
          document.querySelector('[data-action=view][data-value=board]').click();

          const examples=[{title:'Zulu',number:3,priority:'urgent',due:'2026-12-01',createdAt:'2026-01-03T00:00:00Z'},{title:'Alpha',number:1,priority:'low',due:'2026-10-01',createdAt:'2026-01-01T00:00:00Z'},{title:'Beta',number:2,priority:'medium',due:'',createdAt:'2026-01-02T00:00:00Z'}];
          for(const field of ['title','number','priority','manual']){check(smoke.sortTasks([...examples],field,'asc')[0].number===1,field+' ascending');check(smoke.sortTasks([...examples],field,'desc')[0].number===3,field+' descending');}
          for(const direction of ['asc','desc'])check(smoke.sortTasks([...examples],'due',direction).at(-1).number===2,'Undated tasks stay last');

          const toggle=document.querySelector('[data-action=toggle-filters]');toggle.click();check(document.querySelector('#filter-options').hidden,'Filters collapse');check(smoke.getState().settings.layout.filtersCollapsed,'Collapse state saved');document.querySelector('[data-action=toggle-filters]').click();
          const filler=document.createElement('div');filler.style.height='3000px';document.querySelector('.page').append(filler);window.scrollTo(0,600);check(Math.abs(document.querySelector('.heading-actions').getBoundingClientRect().top)<2,'Toolbar stays at viewport top');window.scrollTo(0,0);filler.remove();
          document.body.dispatchEvent(new KeyboardEvent('keydown',{key:'s',bubbles:true}));check(smoke.bulk.selecting,'Select shortcut');document.body.dispatchEvent(new KeyboardEvent('keydown',{key:'s',bubbles:true}));check(!smoke.bulk.selecting,'Selection shortcut toggles off');
          document.body.dispatchEvent(new KeyboardEvent('keydown',{key:'d',bubbles:true}));check(document.querySelector('.receipt-modal'),'Stack shortcut');smoke.closeOverlay(true);
          document.body.dispatchEvent(new KeyboardEvent('keydown',{key:'i',bubbles:true}));check(document.querySelector('#import-file'),'Import shortcut');smoke.closeOverlay(true);

          document.querySelector('[data-qol=capture]').click();
          check(document.querySelector('#modal-form').textContent.includes('Shift'),'Shortcut displayed');
          for(const title of ['Captured one','Captured two']){document.querySelector('#capture-title').value=title;document.querySelector('#modal-form').requestSubmit();}
          check(s.tasks.length===4,'Capture creates multiple tasks');check(document.querySelector('#capture-title').value==='','Capture clears input');
          smoke.closeOverlay(true);
          document.dispatchEvent(new KeyboardEvent('keydown',{key:'k',ctrlKey:true,bubbles:true}));
          const query=document.querySelector('#jump-query');query.value='#2';query.dispatchEvent(new Event('input',{bubbles:true}));
          check(document.querySelectorAll('[data-jump]').length===1,'Jump by number');document.querySelector('[data-jump]').click();
          check(document.querySelector('#task-form').dataset.id===s.tasks[1].id,'Jump opens task');
          const waiting=document.querySelector('[name=waitingOn]');waiting.value='Client';document.querySelector('[name=followUpDate]').value='2020-01-01';document.querySelector('#task-form').requestSubmit();
          check(smoke.qol.reasons(s.tasks[1]).includes('Follow up with Client'),'Follow up enters attention');smoke.power.preset('attention');check(smoke.filtered().some(t=>t.id===s.tasks[1].id),'Quick attention includes waiting');smoke.power.reset();
          document.querySelector('[data-action=scope][data-value=attention]').click();check(document.querySelector('.attention-row'),'Attention rows');
          document.querySelector('[data-qol=follow-up]').click();document.querySelector('[name=resolved]').checked=true;document.querySelector('#modal-form').requestSubmit();
          check(!s.tasks[1].waitingOn,'Resolved waiting');
          smoke.complete(s.tasks[1].id);check(smoke.qol.reasons(s.tasks[0]).includes('Dependencies cleared'),'Cleared dependency alert');
          document.querySelector('[data-qol=acknowledge]').click();check(!smoke.qol.reasons(s.tasks[0]).includes('Dependencies cleared'),'Acknowledgement');
          smoke.complete(s.tasks[1].id);smoke.complete(s.tasks[1].id);check(smoke.qol.reasons(s.tasks[0]).includes('Dependencies cleared'),'New completion resurfaces');
          const beforeStack=JSON.stringify(s.tasks);document.querySelector('[data-action=receipts]').click();
          check(document.querySelectorAll('.order-chit').length===s.tasks.filter(t=>t.status==='done').length,'Daily rails display completed tasks');
          check(document.querySelector('.day-rail'),'Daily rail present');check(!document.querySelector('[data-stack-style]'),'Spike selector removed');
          check(document.querySelector('.order-chit h3').textContent===s.tasks[1].title,'Chit task identity');
          check(JSON.stringify(s.tasks)===beforeStack,'Stack browsing leaves tasks untouched');smoke.closeOverlay(true);
          smoke.qol.saveTemplate(s.tasks[0].id);document.querySelector('[name=name]').value='Course template';document.querySelector('#modal-form').requestSubmit();
          const originalLive=JSON.stringify(s.tasks);
          smoke.qol.editTemplate(s.templates[0].id);
          document.querySelector('[name=title]').value='Edited course';document.querySelector('[name=priority]').value='high';
          document.querySelector('[data-template-add]').click();document.querySelector('[name=title]').value='Extra step';document.querySelector('[data-template-remove]').click();
          document.querySelectorAll('[data-template-task]')[1].click();document.querySelector('[name=title]').value='Edited participant';document.querySelector('[name=checklist]').value='Get evidence\\nRecord completion';
          document.querySelector('#template-editor').requestSubmit();
          check(s.templates[0].tasks[0].title==='Edited course'&&s.templates[0].tasks[1].title==='Edited participant','Direct template editing');
          check(JSON.stringify(s.tasks)===originalLive,'Template edits leave live tasks untouched');
          smoke.closeOverlay(true);smoke.qol.editTemplate();document.querySelector('[name=templateName]').value='Brand new template';document.querySelector('[name=title]').value='Independent task';document.querySelector('#template-editor').requestSubmit();
          check(s.templates.length===2&&JSON.stringify(s.tasks)===originalLive,'Create template without live task');smoke.closeOverlay(true);
          smoke.qol.capture();check(document.querySelectorAll('[data-qol=capture-template]').length===2,'Quick capture lists templates');document.querySelector('#capture-title').value='Course from capture';document.querySelector('[data-qol=capture-template][data-id="'+s.templates[0].id+'"]').click();check(document.querySelector('[name=title]').value==='Course from capture','Capture title carries into template');document.querySelector('[name=anchor]').value='2026-11-02';document.querySelector('#modal-form').requestSubmit();
          const parent=s.tasks.at(-2),child=s.tasks.at(-1);check(parent.id!==s.tasks[0].id&&parent.dependencies[0]===child.id&&child.parentId===parent.id,'Template remaps hierarchy and dependencies');
          check(parent.start==='2026-11-02'&&parent.due==='2027-02-02','Template date shift');check(child.status!=='done'&&!child.completedAt,'Template resets completion');check(parent.priority==='high'&&child.title==='Edited participant'&&child.checklist.length===2,'New tasks use edited template');smoke.closeOverlay(true);
          smoke.bulk.ids=new Set([parent.id,child.id]);smoke.qol.bulkEdit();document.querySelector('[name=apply-priority]').checked=true;document.querySelector('[name=priority]').value='urgent';document.querySelector('#modal-form').requestSubmit();
          check(parent.priority==='urgent'&&child.priority==='urgent','Bulk priority');
          smoke.qol.bulkEdit();document.querySelector('[name=apply-due]').checked=true;document.querySelector('[name=due]').value='2020-01-01';document.querySelector('#modal-form').requestSubmit();check(parent.due==='2027-02-02'&&child.due==='2027-02-02','Invalid bulk edit atomic');smoke.closeOverlay(true);
          document.querySelector('[data-action=scope][data-value=all]').click();document.querySelector('[data-action=sort-tasks][data-value=number]').click();document.querySelector('[data-action=collapse-column]').click();
          document.querySelector('[data-action=sort-direction][data-value=desc]').click();const numbered=smoke.filtered().filter(t=>t.number);check(numbered[0].number>=numbered.at(-1).number,'Direction affects task list');const layout=s.settings.layout;check(layout.sort==='number'&&layout.collapsedColumns.length===1,'Layout captured');smoke.restoreLayout();smoke.render();check(document.querySelector('[data-action=sort-tasks][data-value=number]').classList.contains('selected'),'Layout restored');
          smoke.openTask(s.tasks[2].id);document.querySelector('[data-action=delete-task]').click();
          document.querySelector('[data-action=toggle-filters]').click();
          return 'Sticky toolbar, shortcuts, collapsible filters, capture, switcher, waiting, attention, templates, bulk edits, layout passed';
        '''))
        flush()
        data=store.recovery_list();assert len(data['trash'])==1
        window.evaluate_js('smoke.qol.recovery()')
        for _ in range(100):
            if window.evaluate_js('Boolean(document.querySelector("[data-qol=restore-task]"))'):break
            time.sleep(.05)
        js("document.querySelector('[data-qol=restore-task]').click();return true;")
        for _ in range(100):
            if not store.recovery_list()['trash']:break
            time.sleep(.05)
        else:raise AssertionError('Trash restoration failed')
        flush()
        saved=Store(path).read()
        assert len(saved['tasks'])==6 and saved['settings']['layout']['sort']=='number' and len(saved['templates'])==2
        results.append('Native recovery bridge and persisted workspace passed')
        window.load_html(html)
        for _ in range(100):
            if window.evaluate_js('Boolean(window.smoke && smoke.getState().tasks.length===6)'):break
            time.sleep(.1)
        results.append(js("check(document.querySelector('[data-action=sort-tasks][data-value=number]').classList.contains('selected'),'Sort persisted across reload');check(document.querySelector('[data-action=sort-direction][data-value=desc]').getAttribute('aria-pressed')==='true','Direction persisted across reload');check(document.querySelector('.column-cards[hidden]'),'Collapsed column persisted across reload');check(smoke.getState().templates.length===2,'Templates persisted across reload');check(document.querySelector('#filter-options').hidden,'Collapsed filters persisted across reload');return 'Fresh page restores saved layout and templates';"))
        flush()
    except Exception as exc:results.append('FAILED: '+str(exc))
    finally:
        print(json.dumps(results),flush=True)
        window.destroy()
webview.start(run,gui='edgechromium',http_server=False)
folder.cleanup()
if any('FAILED' in x for x in results):raise SystemExit(1)
