"""Run manually on Windows to exercise the real desktop JavaScript and bridge."""
import base64
import json
from pathlib import Path
import sys
import tempfile
import time
import zipfile
import io
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import webview
from desktop import DesktopAPI,build_html
from importing import apply_import
from storage import Store

folder=tempfile.TemporaryDirectory()
path=Path(folder.name)/'test.sqlite'
store=Store(path)
s=store.read()
s['projects']=[{'id':'zulu','name':'Zulu','color':'#778866','active':True},{'id':'alpha','name':'Alpha','color':'#778866','active':True},{'id':'archived','name':'Archived','color':'#778866','active':False}]
s['tags']=['Zulu','alpha']
s=apply_import({'filename':'tasks.json','content':json.dumps([{'title':'Course','on_radar':True,'review_date':'2026-10-01','review_every_days':14},{'title':'Alex course','delegated_to':'Alex','due':'2026-10-07'}])},s)
s['tasks'][1]['parentId']=s['tasks'][0]['id']
store.save(s)
api=DesktopAPI(path)
html=build_html().replace('window.turboHasUnsavedChanges=', 'window.smoke={power,matchesFilter,filtered,openTask,submitTask,exportExcel,render,complete,bulk,setView:value=>{view=value;render();},getState:()=>state,ready:()=>saveQueue};window.turboHasUnsavedChanges=')
html=html.replace('return (await bridgeReady).save_file(filename,encoded);','window.exportPayload={filename,encoded};return true;')
window=webview.create_window('TurboTodos validation',html=html,js_api=api,hidden=True)
api._window=window
result=[]
def run():
    try:
        for _ in range(100):
            if window.evaluate_js('Boolean(window.smoke)'):break
            time.sleep(.1)
        else:raise AssertionError('UI failed to load')
        assertions=r'''(()=>{
          const {matchesFilter:m,power:p,getState}=smoke,s=getState(),tasks=s.tasks,t=tasks[1],now='2026-10-01';
          const check=(v,msg)=>{if(!v)throw Error(msg)};
          check(m(t,{field:'due',op:'7'},tasks,now),'7-day inclusive end');
          check(!m({...t,due:'2026-10-08'},{field:'due',op:'7'},tasks,now),'7-day excluded end');
          check(!m({...t,due:'2026-09-30'},{field:'due',op:'7'},tasks,now),'overdue excluded');
          check(m({...t,due:'2026-09-30'},{field:'due',op:'7',includeOverdue:true},tasks,now),'overdue toggle');
          check(m({...t,due:'2026-10-04'},{field:'due',op:'week'},tasks,now),'Sunday included');
          check(!m({...t,due:'2026-10-05'},{field:'due',op:'week'},tasks,now),'Monday excluded');
          check(m({...t,due:'2026-10-31'},{field:'due',op:'month'},tasks,now),'month end');
          check(m(t,{field:'delegated',op:'person',value:'alex'},tasks,now),'delegation');
          check(m(tasks[0],{mode:'all',rules:[{field:'status',op:'active'},{mode:'any',rules:[{field:'due',op:'overdue'},{field:'review',op:'due'}]}]},tasks,now),'nested all/any');
          check(p.visible(tasks).length===1,'collapsed subtasks');
          document.querySelector('[data-power=expand]').click();
          check(p.visible(tasks).length===2,'expanded subtasks');
          p.preset('7');check(smoke.filtered().length===1,'filtered subtask visible');p.reset();
          smoke.openTask(t.id);
          check(document.querySelector('[name=parentId] option:checked').textContent.includes('#1'),'Parent choice includes number');
          document.querySelector('#open-parent').click();
          check(document.querySelector('#task-form').dataset.id===s.tasks[0].id,'Open parent navigation');
          check(document.querySelector('#open-parent').hidden,'Top-level task has no parent jump');
          smoke.openTask(t.id);document.querySelector('[name=delegatedTo]').value='Priya';smoke.submitTask();
          p.filters();check(document.querySelector('.filter-group'),'filter builder');
          return 'Filter boundaries, hierarchy, details and builder passed';
        })()'''
        result.append(window.evaluate_js(assertions))
        for _ in range(100):
            if store.read()['tasks'][1].get('delegatedTo')=='Priya':break
            time.sleep(.1)
        else:raise AssertionError('Desktop save did not persist')
        # Exercise an actual review and check that deadlines/status stay unchanged.
        window.evaluate_js("document.querySelector('[data-action=close]').click();smoke.power.review(smoke.getState().tasks[0].id);document.querySelector('[name=note]').value='7 of 12 complete';document.querySelector('#modal-form').requestSubmit();")
        for _ in range(100):
            reviewed=store.read()['tasks'][0]
            if reviewed.get('reviewHistory'):break
            time.sleep(.1)
        else:raise AssertionError('Review did not persist')
        assert reviewed['reviewHistory'][0]['note']=='7 of 12 complete'
        assert reviewed['status']=='backlog' and reviewed['due']==''
        result.append('Desktop saves and review persistence passed')
        window.evaluate_js("smoke.power.preset('attention');smoke.power.filters();document.querySelector('#view-name').value='Attention';document.querySelector('[data-power=save-view]').click();")
        for _ in range(100):
            if store.read().get('savedViews'):break
            time.sleep(.1)
        else:raise AssertionError('Saved view did not persist')
        window.evaluate_js("smoke.exportExcel(smoke.getState().tasks,smoke.getState());void 0")
        for _ in range(100):
            payload=window.evaluate_js('window.exportPayload||null')
            if payload:break
            time.sleep(.1)
        else:raise AssertionError('Export failed')
        with zipfile.ZipFile(io.BytesIO(base64.b64decode(payload['encoded']))) as workbook:
            sheet=workbook.read('xl/worksheets/sheet1.xml').decode()
            assert 'Review history' in sheet and 'Priya' in sheet and '7 of 12 complete' in sheet
            assert 'A1:X3' in sheet
        result.append('Saved views and Excel metadata passed')
        checks=r'''(()=>{
          const check=(v,msg)=>{if(!v)throw Error(msg)},s=smoke.getState(),id=s.tasks[1].id;
          smoke.power.reset();smoke.setView('grid');
          const search=document.querySelector('#search'),row=document.querySelector('[data-task="'+id+'"]');
          search.focus();search.setSelectionRange(0,0);smoke.render();
          check(document.querySelector('#search')===search&&document.activeElement===search,'Search focus preserved');
          check(document.querySelector('[data-task="'+id+'"]')===row,'Unchanged row preserved');
          const priority=row.querySelector('[data-inline=priority]');priority.value='high';priority.dispatchEvent(new Event('change',{bubbles:true}));
          check(smoke.getState().tasks.find(t=>t.id===id).priority==='high','Inline edit');
          check(document.querySelector('[data-task="'+id+'"] [data-inline=priority]').value==='high','Native control synchronized');
          smoke.bulk.action('toggle');const checkbox=document.querySelector('[data-bulk-select="'+id+'"]');checkbox.click();
          check(smoke.bulk.ids.has(id)&&document.querySelector('[data-bulk-select="'+id+'"]').checked,'Bulk selection retained');
          smoke.complete(id);check(smoke.getState().tasks.find(t=>t.id===id).status==='done','Completion');
          document.querySelector('[data-action=undo]').click();check(smoke.getState().tasks.find(t=>t.id===id).status!=='done','Undo completion');
          check(document.querySelectorAll('.task-row').length===2,'No missing or duplicate rows');
          const m=smoke.matchesFilter,task={...s.tasks[1],priority:'high',tags:['A','B'],due:'2026-10-07',delegatedTo:'Priya'};
          check(m(task,{field:'priority',op:'is',value:['high','urgent']},s.tasks),'Multi priority');
          check(!m(task,{field:'priority',op:'isNot',value:['high','urgent']},s.tasks),'Exclusion');
          check(m(task,{field:'tags',op:'all',value:['A','B']},s.tasks),'All tags');
          check(m(task,{field:'delegated',op:'person',value:['Alex','Priya']},s.tasks),'Multiple people');
          check(m(task,{field:'due',op:['overdue','7']},s.tasks,'2026-10-01'),'Multiple date choices');
          check(m(task,{field:'due',op:[]},s.tasks),'Empty selections unrestricted');
          check(document.querySelector('.standalone-filters'),'Standalone filters visible');
          const chooser=document.querySelector('[data-multi=basic-priority]');
          chooser.querySelector('[value=high]').click();document.querySelector('[data-multi=basic-priority] [value=urgent]').click();
          check(document.querySelectorAll('[data-multi=basic-priority] input:checked').length===2,'Multiple basic choices');
          check(document.querySelector('[data-multi=basic-priority]').tagName==='FIELDSET','Choices always visible');
          check(smoke.filtered().every(t=>['high','urgent'].includes(t.priority)),'Basic multi matching');
          document.querySelector('[data-action=clear-filters]').click();
          smoke.power.filters();document.querySelector('[data-filter-add]').click();
          const dueMenu=document.querySelector('[data-multi="ops:0"]');dueMenu.open=true;
          dueMenu.querySelector('[value=overdue]').click();
          check(document.querySelector('[data-multi="ops:0"]').open,'Advanced menu stays open');
          check(document.querySelectorAll('[data-multi="ops:0"] input:checked').length===2,'Multiple advanced choices');
          document.querySelector('#view-name').value='Multi dates';document.querySelector('[data-power=save-view]').click();
          check(Array.isArray(smoke.getState().savedViews.find(v=>v.name==='Multi dates').filter.rules[0].op),'Saved multi values');
          document.querySelector('[data-action=shortcuts]').click();
          check(document.querySelector('[role=dialog]').textContent.includes('F1'),'Help contains shortcuts');
          document.querySelector('[data-action=close]').click();
          document.dispatchEvent(new KeyboardEvent('keydown',{key:'F1',bubbles:true}));
          check(document.querySelector('[role=dialog]').textContent.includes('Filtering'),'F1 opens help');
          document.querySelector('[data-action=close]').click();
          smoke.openTask(id);const title=document.querySelector('#task-title');title.value='Unsaved draft';title.dispatchEvent(new Event('input',{bubbles:true}));
          document.dispatchEvent(new KeyboardEvent('keydown',{key:'F1',bubbles:true}));document.querySelector('[data-action=close]').click();
          check(document.querySelector('#task-title')===title&&title.value==='Unsaved draft','Help preserves unsaved edits');
          smoke.submitTask();
          smoke.power.reset();smoke.render();
          check(!document.querySelector('.summary'),'Stack banner removed');
          check(!document.body.textContent.includes('YOUR SPACE TO MAKE THINGS HAPPEN'),'Eyebrow removed');
          check(document.querySelector('.heading-actions [data-action=receipts]'),'Stack action in header');
          check(document.querySelector('[data-multi=quick-dates]').tagName==='FIELDSET','Quick dates visible');
          smoke.complete(id);document.querySelector('#show-done').click();
          check(!smoke.filtered().some(t=>t.id===id),'Hide done');
          document.querySelector('#show-done').click();check(smoke.filtered().some(t=>t.id===id),'Show done');
          smoke.complete(id);
          document.querySelector('[data-multi=basic-priority] [value=high]').click();
          document.querySelector('[data-multi=quick-dates] [value="7"]').click();
          check(document.querySelector('[data-multi=basic-priority] [value=high]').checked,'Date selection preserves other filters');
          check(smoke.filtered().every(t=>t.priority==='high'),'Date and priority combine');
          document.querySelector('[data-action=clear-filters]').click();
          return 'Incremental UI, standalone filters, show/hide done and Help passed';
        })()'''
        result.append(window.evaluate_js(checks))
        result.append(window.evaluate_js(r"""(()=>{
          const check=(v,msg)=>{if(!v)throw Error(msg)};
          document.querySelector('[data-action=manage-projects]').click();
          document.querySelector('[data-action=archive-project][data-id=zulu]').click();
          check(smoke.getState().projects.find(p=>p.id==='zulu').active===false,'Project archived');
          document.querySelector('[data-action=close]').click();smoke.openTask(null);
          check(!document.querySelector('select[name=status],select[name=priority],select[name=project]'),'Visible choice fields');
          check([...document.querySelectorAll('[name=project]')].map(i=>i.value).join(',')===',alpha','Only active projects');
          check([...document.querySelectorAll('[name=tags]')].map(i=>i.value).join(',')==='alpha,Zulu','Tags alphabetical');
          check(document.querySelector('#dependencies').textContent.includes('#1'),'Dependency task numbers');
          document.querySelector('#task-title').value='Visible choices task';
          document.querySelector('[name=status][value=next]').click();document.querySelector('[name=priority][value=urgent]').click();
          document.querySelector('[name=project][value=alpha]').click();document.querySelector('[name=tags][value=alpha]').click();
          document.querySelector('[name=newTags]').value='New tag';smoke.submitTask();
          const task=smoke.getState().tasks.find(t=>t.title==='Visible choices task');
          check(task.status==='next'&&task.priority==='urgent'&&task.project==='alpha','Choice values saved');
          check(task.tags.includes('alpha')&&task.tags.includes('New tag'),'Existing and new tags saved');
          check(smoke.power.progress({id:'leaf',status:'backlog'})==='not-started','Unstarted leaf');
          check(smoke.power.progress({id:'leaf',status:'doing'})==='partial','Partial leaf');
          check(smoke.power.progress({id:'leaf',status:'done'})==='completed','Completed leaf');
          const parent=smoke.getState().tasks[0],child=smoke.getState().tasks[1],previous=child.status;
          child.status='backlog';check(smoke.power.progress(parent)==='not-started','Unstarted parent');
          child.status='doing';check(smoke.power.progress(parent)==='partial','Partial parent');
          child.status='done';check(smoke.power.progress(parent)==='completed'&&parent.status!=='done','Completed subtasks preserve parent status');child.status=previous;
          smoke.render();document.querySelector('[data-multi=basic-progress] [value=not-started]').click();
          check(smoke.filtered().every(t=>smoke.power.progress(t)==='not-started'),'Progress filter');
          document.querySelector('[data-action=sort-tasks][data-value=title]').click();
          const names=smoke.filtered().map(t=>t.title);
          check(names.join()===names.slice().sort((a,b)=>a.localeCompare(b)).join(),'Sort buttons');
          document.querySelector('[data-action=clear-filters]').click();
          document.querySelector('[data-action=color-tasks][data-value=deadline]').click();
          check(smoke.getState().settings.coloring==='deadline','Color choice updated');
          check(document.querySelector('[data-action=color-tasks][data-value=deadline]').getAttribute('aria-pressed')==='true','Color choice selected');
          document.querySelector('[data-action=sort-tasks][data-value=number]').click();
          const numbers=smoke.filtered().filter(t=>t.number).map(t=>t.number);
          check(numbers.every((n,i)=>i===0||numbers[i-1]<=n),'Numeric task-number sort');
          const visible=smoke.filtered(),open=visible.filter(t=>t.status!=='done').length;
          check(document.querySelector('.task-count').textContent===`${visible.length} task${visible.length===1?'':'s'} (${open} open)`,'Filtered open-task count');
          smoke.openTask(task.id);const draftTitle=document.querySelector('#task-title');draftTitle.value='Zoom keeps draft';
          document.querySelector('[data-action=zoom-in]').click();
          check(smoke.getState().settings.zoom===110,'Zoom increases');
          check(document.querySelector('#task-title')===draftTitle&&draftTitle.value==='Zoom keeps draft','Zoom preserves task draft');
          for(let i=0;i<12;i++)document.dispatchEvent(new KeyboardEvent('keydown',{key:'+',ctrlKey:true,bubbles:true}));
          check(smoke.getState().settings.zoom===180,'Maximum zoom');
          check(parseFloat(getComputedStyle(document.documentElement).zoom)===1.8,'Zoom applied');
          const bounds=document.querySelector('.drawer').getBoundingClientRect();
          check(bounds.right<=innerWidth+2&&bounds.bottom<=innerHeight+2,'Zoomed drawer stays in viewport');
          for(let i=0;i<15;i++)document.dispatchEvent(new KeyboardEvent('keydown',{key:'-',ctrlKey:true,bubbles:true}));
          check(smoke.getState().settings.zoom===80,'Minimum zoom');
          document.dispatchEvent(new KeyboardEvent('keydown',{key:'0',ctrlKey:true,bubbles:true}));
          check(smoke.getState().settings.zoom===100,'Zoom resets');
          return 'Task entry, filters, controls, counts, zoom limits and draft preservation passed';
        })()"""))
        window.evaluate_js('smoke.ready().then(()=>window.allSaved=true);void 0')
        for _ in range(100):
            if window.evaluate_js('Boolean(window.allSaved)'):break
            time.sleep(.05)
        else:raise AssertionError('Save queue did not finish')
        saved_new=store.read()['tasks'][-1]
        assert saved_new['title']=='Visible choices task' and saved_new['number']==3
        assert window.evaluate_js("smoke.getState().tasks.at(-1).number")==3
        for _ in range(100):
            persisted=store.read()['tasks'][1]
            if persisted['priority']=='high' and persisted['status']!='done':break
            time.sleep(.1)
        else:raise AssertionError('Rapid edits did not persist')
    except Exception as exc:
        result.append('FAILED: '+str(exc))
    finally:
        print(json.dumps(result),flush=True)
        window.destroy()
webview.start(run,gui='edgechromium',http_server=False)
folder.cleanup()
if any('FAILED' in s for s in result):raise SystemExit(1)
