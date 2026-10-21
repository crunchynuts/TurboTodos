import { apiFetch } from './transport.js';
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const day=()=>{const d=new Date();return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;};
const $=s=>document.querySelector(s);
let host;
export const qol={
 configure(h){host=h;},
 task(title,extra={}){return {id:host.uid(),title,status:host.state().columns.find(c=>!['done','cancelled'].includes(c.id)).id,project:host.power.defaultProject(),priority:'medium',tags:[],start:'',due:'',notes:'',dependencies:[],checklist:[],reminder:'',remindedAt:'',completedAt:'',createdAt:new Date().toISOString(),milestone:false,parentId:'',...extra};},
 reasons(t){return host.power.attention(t);},
 signature(t){return [...t.dependencies].sort().map(id=>id+':'+(host.task(id)?.completedAt||'done')).join('|');},
 meta(t){const waiting=t.dependencies.map(id=>host.task(id)).filter(x=>x&&x.status!=='done');return `<div class="qol-meta">${t.waitingOn?`<span>Waiting on <b>${esc(t.waitingOn)}</b>${t.followUpDate?' · follow up '+esc(t.followUpDate):''}</span>`:''}${waiting.length?`<span>Blocked by ${waiting.map(x=>`<button type="button" class="text-button" data-power="open" data-id="${x.id}" title="${esc(x.title)}">#${x.number||'…'} · ${esc(x.title)}</button>`).join(', ')}</span>`:''}</div>`;},
 capture(){
  if(!host.leave())return;
  host.dialog('Quick capture',`<label class="modal-label">Task title<input name="title" id="capture-title" required maxlength="500" placeholder="Type a task, press Enter, repeat…"></label><p class="field-help"><kbd>Ctrl</kbd> + <kbd>Shift</kbd> + <kbd>N</kbd> opens Quick capture. Enter adds a task and keeps this window open; Esc closes it.</p><p class="field-help">Creates a task in the first open column, with your default project and no tags. Add details later.</p><p id="capture-status" role="status"></p><section class="capture-templates" aria-labelledby="capture-templates-heading"><h3 id="capture-templates-heading">Or use a template <span class="selection-count">${(host.state().templates||[]).length}</span></h3><p class="field-help">Choose a template to set its title and schedule. Any title typed above carries over.</p><div class="capture-template-list" role="region" aria-label="Available task templates" tabindex="0">${[...(host.state().templates||[])].sort((a,b)=>a.name.localeCompare(b.name,undefined,{sensitivity:'base',numeric:true})).map(t=>`<button type="button" class="capture-template" data-qol="capture-template" data-id="${esc(t.id)}"><strong>${esc(t.name)}</strong><small>${t.tasks.length} task${t.tasks.length===1?'':'s'}${t.tasks.length>1?' · includes subtasks':''}</small><span aria-hidden="true">→</span></button>`).join('')||'<p class="field-help">No templates yet. Create one in Task templates, or choose Save template on a task.</p>'}</div></section>`,f=>{
   const title=f.get('title').trim();if(!title)return;
   if(host.state().tasks.length>=10000){host.toast('The workspace limit is 10,000 tasks.');return;}
   host.mutate(()=>host.state().tasks.push(this.task(title)),'Task captured');
   $('#capture-title').value='';$('#capture-status').textContent='Added: '+title;host.clean();$('#capture-title').focus();
  },'Add & keep open');
 },
 switcher(){
  if(!host.leave())return;
  host.dialog('Jump to task',`<label class="modal-label">Task number or title<input id="jump-query" placeholder="#24 or course…" autocomplete="off"></label><div id="jump-results" class="qol-list"></div>`,()=>$('#jump-results button')?.click(),'Open first result');
  const draw=()=>{const q=$('#jump-query').value.trim().toLowerCase(),tasks=host.state().tasks.filter(t=>!q||('#'+t.number+' '+t.title).toLowerCase().includes(q)).slice(0,40);$('#jump-results').innerHTML=tasks.map(t=>`<button type="button" class="subtask-link" data-jump="${t.id}"><b>#${t.number||'…'}</b> ${esc(t.title)} <small>${t.status==='done'?'Done':''}</small></button>`).join('')||'<p>No matching tasks.</p>';};
  $('#jump-query').addEventListener('input',()=>{draw();host.clean();});
  $('#jump-results').addEventListener('click',e=>{const b=e.target.closest('[data-jump]');if(b){host.close(true);host.open(b.dataset.jump);}});draw();
 },
 attention(tasks){return `<div class="attention-list">${tasks.map(t=>`<article class="attention-row"><button class="text-button" data-power="open" data-id="${t.id}"><strong>#${t.number||'…'} · ${esc(t.title)}</strong></button><div>${this.reasons(t).map(r=>`<span class="tag">${esc(r)}</span>`).join(' ')}</div>${this.meta(t)}<div>${t.waitingOn?`<button class="button small" data-qol="follow-up" data-id="${t.id}">Followed up</button>`:''}${t.reviewDate?`<button class="button small" data-power="review" data-id="${t.id}">Review</button>`:''}${this.reasons(t).includes('Dependencies cleared')?`<button class="button small" data-qol="acknowledge" data-id="${t.id}">Got it</button>`:''}${t.reminder&&new Date(t.reminder)<=new Date()?`<button class="button small" data-qol="dismiss-reminder" data-id="${t.id}">Dismiss reminder</button>`:''}<button class="button small" data-action="complete" data-id="${t.id}">Done</button></div></article>`).join('')||'<p class="empty-column">Nothing needs attention right now.</p>'}</div>`;},
 followUp(id){const t=host.task(id);if(!t||!host.leave())return;host.dialog('Follow up · '+t.title,`<label class="modal-label">Update<textarea name="note" maxlength="5000" rows="3"></textarea></label><label class="modal-label">Next follow-up<input name="date" type="date"></label><label><input name="resolved" type="checkbox"> No longer waiting</label><p class="field-help">Leave the date blank to clear this follow-up. The task and its deadline stay unchanged.</p>`,f=>{if((t.reviewHistory||[]).length>=1000){host.toast('Review history is full.');return;}host.mutate(()=>{t.reviewHistory=[...(t.reviewHistory||[]),{at:new Date().toISOString(),note:'Follow-up: '+(f.get('note').trim()||'Checked in')}];t.followUpDate=f.has('resolved')?'':f.get('date');if(f.has('resolved'))t.waitingOn='';},'Follow-up recorded');host.close(true);},'Save follow-up');},
 bulkEdit(){
  const tasks=host.state().tasks.filter(t=>host.bulk.ids.has(t.id));if(!tasks.length)return;
  const choices=(name,values)=>`<label class="modal-label"><input type="checkbox" name="apply-${name}"> Change ${name}<select name="${name}">${values.map(([v,n])=>`<option value="${esc(v)}">${esc(n)}</option>`).join('')}</select></label>`;
  host.dialog('Edit '+tasks.length+' selected tasks',`<p class="field-help">Only checked fields change. Selection includes tasks outside the current filter.</p>${choices('status',host.state().columns.map(c=>[c.id,c.name]))}${choices('priority',['low','medium','high','urgent'].map(v=>[v,v]))}${choices('project',[['','No project'],...host.state().projects.filter(p=>p.active!==false).sort((a,b)=>a.name.localeCompare(b.name)).map(p=>[p.id,p.name])])}<label class="modal-label"><input name="apply-due" type="checkbox"> Change deadline<input name="due" type="date"></label><label class="modal-label"><input name="apply-delegatedTo" type="checkbox"> Change delegated person<input name="delegatedTo" maxlength="200"></label><p class="field-help">A checked field with a blank value clears that value.</p>`,f=>{
   const changes={};for(const field of ['status','priority','project','due','delegatedTo'])if(f.has('apply-'+field))changes[field]=f.get(field).trim();
   if(!Object.keys(changes).length){host.toast('Check at least one field to change.');return;}
   if(changes.due&&tasks.some(t=>t.start&&t.start>changes.due)){host.toast('The deadline precedes a selected task’s start date. No tasks changed.');return;}
   if(changes.status==='done'&&tasks.some(t=>t.status!=='done'&&host.state().tasks.some(c=>c.parentId===t.id&&c.status!=='done'&&!host.bulk.ids.has(c.id)))&&!confirm('Some selected parents have incomplete subtasks outside this selection. Complete the selected parents anyway?'))return;
   host.mutate(()=>{for(const t of tasks){Object.assign(t,changes);if('status'in changes)t.completedAt=changes.status==='done'?(t.completedAt||new Date().toISOString()):'';}},tasks.length+' tasks updated');host.close(true);
  },'Apply changes');
 },
 templates(){
  if(!host.leave())return;
  const templates=host.state().templates||[];
  host.dialog('Task templates',`<p class="field-help">Create and edit templates here independently of live tasks, or save a task as a starting point. New copies reset completion, reviews, waiting follow-ups, and reminders. Dates shift relative to the start date you choose.</p><button type="button" class="button" data-qol="new-template">+ New template</button><div class="qol-list">${templates.map(t=>`<div class="template-row"><span><b>${esc(t.name)}</b><small>${t.tasks.length} task(s)</small></span><button class="button" type="button" data-qol="edit-template" data-id="${esc(t.id)}">Edit</button><button class="button" type="button" data-qol="use-template" data-id="${esc(t.id)}">Use</button><button class="text-button danger" type="button" data-qol="delete-template" data-id="${esc(t.id)}">Delete</button></div>`).join('')||'<p>No templates yet. Create one in Task templates, or choose Save template on a task.</p>'}</div>`,()=>host.close(true),'Done');
 },
 editTemplate(id){
  if(!host.leave())return;
  const existing=(host.state().templates||[]).find(t=>t.id===id);
  if(!existing&&(host.state().templates||[]).length>=100){host.toast('Keep at most 100 templates.');return;}
  const draft=existing?structuredClone(existing):{id:host.uid(),name:'',tasks:[this.task('New task')]};
  let selected=draft.tasks[0].id;
  const sync=()=>{
   const form=$('#template-editor');if(!form)return;
   const f=new FormData(form),t=draft.tasks.find(t=>t.id===selected);
   draft.name=f.get('templateName').trim();t.title=f.get('title').trim();t.priority=f.get('priority');t.project=f.get('project');
   t.tags=[...new Set(f.get('tags').split(',').map(x=>x.trim()).filter(Boolean))];
   t.start=f.get('start');t.due=f.get('due');t.delegatedTo=f.get('delegatedTo').trim();t.waitingOn=f.get('waitingOn').trim();
   t.onRadar=f.has('onRadar');t.milestone=f.has('milestone');t.reviewEveryDays=Number(f.get('reviewEveryDays')||0);
   t.notes=host.cleanHTML($('#template-notes').innerHTML);
   t.checklist=f.get('checklist').split('\n').map(x=>x.trim()).filter(Boolean).map(text=>({id:host.uid(),text,done:false}));
   t.dependencies=f.getAll('dependency');
  };
  const draw=()=>{
   const t=draft.tasks.find(t=>t.id===selected),root=draft.tasks[0];
   const options=(items,value)=>items.map(([v,n])=>`<option value="${esc(v)}" ${v===value?'selected':''}>${esc(n)}</option>`).join('');
   host.dialog(existing?'Edit template':'New template',`<div id="template-editor-fields"><label class="modal-label">Template name<input name="templateName" required maxlength="100" value="${esc(draft.name)}"></label><p class="field-help">Edits apply only to this template. Existing tasks stay unchanged. Start/due dates are a reusable schedule; they shift when you use the template.</p><div class="template-editor-layout"><nav class="template-task-list" aria-label="Template tasks">${draft.tasks.map((x,i)=>`<button type="button" data-template-task="${x.id}" class="${x.id===selected?'selected':''}" aria-pressed="${x.id===selected}"><small>${i?'Subtask':'Main task'}</small>${esc(x.title)||'Untitled'}</button>`).join('')}<button type="button" data-template-add>+ Add subtask</button></nav><section class="template-task-fields"><h3>${t===root?'Main task':'Subtask'}</h3><label class="modal-label">Task title<input name="title" required maxlength="500" value="${esc(t.title)}"></label><div class="detail-fields"><label>Priority<select name="priority">${options(['low','medium','high','urgent'].map(p=>[p,p]),t.priority)}</select></label><label>Project<select name="project">${options([['','No project'],...host.state().projects.filter(p=>p.active!==false||p.id===t.project).sort((a,b)=>a.name.localeCompare(b.name)).map(p=>[p.id,p.name+(p.active===false?' (archived)':'')])],t.project)}</select></label><label>Start date<input name="start" type="date" value="${esc(t.start)}"></label><label>Due date<input name="due" type="date" value="${esc(t.due)}"></label><label>Delegated to<input name="delegatedTo" maxlength="200" value="${esc(t.delegatedTo)}"></label><label>Waiting on<input name="waitingOn" maxlength="200" value="${esc(t.waitingOn)}"></label><label>Review every (days)<input name="reviewEveryDays" type="number" min="0" max="3650" value="${t.reviewEveryDays||0}"></label><label><input type="checkbox" name="onRadar" ${t.onRadar?'checked':''}> Keep on Radar</label><label><input type="checkbox" name="milestone" ${t.milestone?'checked':''}> Milestone</label></div><label class="modal-label">Tags (comma-separated)<input name="tags" value="${esc(t.tags.join(', '))}"></label><label class="modal-label">Checklist (one step per line)<textarea name="checklist" rows="4">${esc(t.checklist.map(c=>c.text).join('\n'))}</textarea></label><label class="modal-label">Notes</label><div class="rich-editor"><div class="rich-toolbar"><button type="button" data-template-format="bold"><b>B</b></button><button type="button" data-template-format="italic"><i>I</i></button><button type="button" data-template-format="insertUnorderedList">• List</button></div><div id="template-notes" contenteditable="true" role="textbox" aria-label="Template notes" aria-multiline="true">${host.cleanHTML(t.notes)}</div></div><fieldset class="template-dependencies"><legend>Depends on (within this template)</legend>${draft.tasks.filter(x=>x.id!==t.id).map(x=>`<label><input name="dependency" type="checkbox" value="${x.id}" ${t.dependencies.includes(x.id)?'checked':''}> ${esc(x.title)}</label>`).join('')||'<small>Add a subtask to create dependencies.</small>'}</fieldset>${t!==root?'<button type="button" class="text-button danger" data-template-remove>Remove this subtask</button>':''}</section></div><p id="template-error" class="inline-error" role="alert"></p></div>`,()=>{
    sync();let error='';
    if(!draft.name)error='Give the template a name.';
    for(const t of draft.tasks){if(!t.title)error='Every task needs a title.';if(!Number.isInteger(t.reviewEveryDays)||t.reviewEveryDays<0||t.reviewEveryDays>3650)error='Review cadence must be 0 to 3650 days.';if(t.start&&t.due&&t.start>t.due)error='Due date precedes start date: '+t.title;if(t.tags.length>200||t.tags.some(x=>x.length>100))error='Use at most 200 tags, each under 100 characters.';if(t.checklist.some(c=>c.text.length>2000))error='Checklist steps must be under 2,000 characters.';if(t.notes.length>200000)error='Notes are too long.';}
    const byId=new Map(draft.tasks.map(x=>[x.id,x])),visiting=new Set(),visited=new Set();
    const cycle=id=>{if(visiting.has(id))return true;if(visited.has(id))return false;visiting.add(id);if(byId.get(id).dependencies.some(cycle))return true;visiting.delete(id);visited.add(id);return false;};
    if(draft.tasks.some(t=>cycle(t.id)))error='Dependencies cannot form a cycle.';
    if(error){$('#template-error').textContent=error;return;}
    host.mutate(()=>{host.state().templates??=[];const index=host.state().templates.findIndex(x=>x.id===draft.id);if(index<0)host.state().templates.push(structuredClone(draft));else host.state().templates[index]=structuredClone(draft);},'Template saved');host.close(true);this.templates();
   },'Save template');
   const form=$('#modal-form');form.id='template-editor';form.closest('.modal').classList.add('template-editor-modal');
   $('#template-notes').addEventListener('paste',e=>{e.preventDefault();document.execCommand('insertText',false,e.clipboardData.getData('text/plain'));});
   form.addEventListener('mousedown',e=>{if(e.target.closest('[data-template-format]'))e.preventDefault();});
   form.addEventListener('click',e=>{
    const button=e.target.closest('[data-template-task],[data-template-add],[data-template-remove],[data-template-format]');if(!button)return;
    if(button.dataset.templateFormat){document.execCommand(button.dataset.templateFormat,false);host.dirty();return;}
    sync();
    if(button.hasAttribute('data-template-task'))selected=button.dataset.templateTask;
    if(button.hasAttribute('data-template-add')){if(draft.tasks.length>=500){host.toast('Templates support at most 500 tasks.');return;}const child=this.task('New subtask',{parentId:root.id});draft.tasks.push(child);selected=child.id;}
    if(button.hasAttribute('data-template-remove')){draft.tasks=draft.tasks.filter(x=>x.id!==selected);for(const x of draft.tasks)x.dependencies=x.dependencies.filter(d=>d!==selected);selected=root.id;}
    draw();host.dirty();
   });
  };draw();
 },
 saveTemplate(id){
  const t=host.task(id);if(!t||!host.leave())return;
  host.dialog('Save task template',`<label class="modal-label">Template name<input name="name" required maxlength="100" value="${esc(t.title.slice(0,100))}"></label><p class="field-help">Includes this task, its checklist, and direct subtasks. Dependencies between included tasks are kept; links to other tasks are omitted.</p>`,f=>{
   if((host.state().templates||[]).length>=100){host.toast('Keep at most 100 templates.');return;}
   const tasks=structuredClone([t,...host.state().tasks.filter(c=>c.parentId===t.id)]),ids=new Set(tasks.map(x=>x.id));
   for(const x of tasks){x.dependencies=x.dependencies.filter(d=>ids.has(d));if(!ids.has(x.parentId))x.parentId='';}
   if(tasks.length>500){host.toast('Templates support at most 500 tasks.');return;}
   host.mutate(()=>{host.state().templates??=[];host.state().templates.push({id:host.uid(),name:f.get('name').trim(),tasks});},'Template saved');host.close(true);
  },'Save template');
 },
 useTemplate(id,titleOverride=''){
  const template=host.state().templates?.find(t=>t.id===id);if(!template)return;
  host.dialog('Use template · '+template.name,`<label class="modal-label">New parent / task title<input name="title" required maxlength="500" value="${esc(titleOverride||template.tasks[0].title)}"></label><label class="modal-label">Schedule anchor<input name="anchor" type="date" required value="${day()}"></label><p class="field-help">The earliest start or due date moves to this date; other dates keep their spacing. Undated tasks remain undated. Archived projects are cleared.</p>`,f=>{
   if(host.state().tasks.length+template.tasks.length>10000){host.toast('This would exceed 10,000 tasks.');return;}
   const tasks=structuredClone(template.tasks),ids=new Map(tasks.map(t=>[t.id,host.uid()]));
   const dates=tasks.flatMap(t=>[t.start,t.due]).filter(Boolean).sort(),base=dates[0];
   const offset=base?Math.round((new Date(f.get('anchor')+'T12:00:00Z')-new Date(base+'T12:00:00Z'))/86400000):0;
   const shift=d=>{if(!d)return '';const date=new Date(d+'T12:00:00Z');date.setUTCDate(date.getUTCDate()+offset);return date.toISOString().slice(0,10);};
   for(const t of tasks){t.id=ids.get(t.id);delete t.number;delete t.sourceKey;t.title=t===tasks[0]?f.get('title').trim():t.title;t.parentId=ids.get(t.parentId)||'';t.dependencies=t.dependencies.map(d=>ids.get(d)).filter(Boolean);t.status=host.state().columns.find(c=>!['done','cancelled'].includes(c.id)).id;t.project=host.state().projects.find(p=>p.id===t.project&&p.active!==false)?.id||'';t.start=shift(t.start);t.due=shift(t.due);t.completedAt='';t.createdAt=new Date().toISOString();t.reminder='';t.remindedAt='';t.reviewDate='';t.reviewHistory=[];t.followUpDate='';t.readyAcknowledged='';t.checklist=t.checklist.map(c=>({...c,id:host.uid(),done:false}));}
   host.mutate(()=>{host.state().tasks.push(...tasks);host.state().tags=[...new Set([...host.state().tags,...tasks.flatMap(t=>t.tags)])];},tasks.length+' tasks created');host.close(true);host.open(tasks[0].id);
  },'Create tasks');
 },
 async recovery(){
  if(!host.leave())return;
  try{await host.ready();const r=await apiFetch('/api/recovery'),data=await r.json();if(!r.ok)throw Error(data.error);
   host.dialog('Trash & backups',`<p class="field-help">Deleted tasks stay here until restored. Restoring a task keeps its number and any parent/dependencies that still exist; detached child and incoming dependency links are not recreated.</p><h3>Deleted tasks</h3><div class="qol-list">${data.trash.map(x=>`<div class="template-row"><span>#${x.task.number||'…'} · ${esc(x.task.title)}<small>${esc(new Date(x.deletedAt).toLocaleString())}</small></span><button type="button" class="button" data-qol="restore-task" data-id="${x.id}">Restore</button></div>`).join('')||'<p>Trash is empty.</p>'}</div><h3>Automatic backups</h3><p class="field-help">Up to 30 local snapshots, taken before the first change and then at most once an hour when editing. A recovery also takes a safety snapshot. Restoring a backup replaces the workspace; task numbers remain stable.</p><div class="qol-list">${data.backups.map(x=>`<div class="template-row"><span>${esc(new Date(x.at).toLocaleString())}</span><button type="button" class="button" data-qol="restore-backup" data-id="${x.name}">Restore workspace</button></div>`).join('')||'<p>No snapshots yet.</p>'}</div>`,()=>host.close(true),'Done');
  }catch(e){host.toast('Could not load recovery: '+e.message);}
 },
 async restore(id,backup=false){
  if(host.bulk.busy)return;
  if(backup&&!confirm('Replace the entire workspace with this backup? A safety snapshot of the current workspace will be kept.'))return;
  host.bulk.busy=true;
  try{await host.ready();const r=await apiFetch('/api/recovery',{method:'POST',body:{version:host.state().version,...(backup?{backup:id}:{id})}}),s=await r.json();if(!r.ok)throw Error(s.error);host.accept(s,backup?'Workspace restored':'Task restored');host.close(true);}
  catch(e){host.toast('Recovery failed: '+e.message);}finally{host.bulk.busy=false;}
 }
};
document.addEventListener('click',e=>{const b=e.target.closest('[data-qol]');if(!b)return;e.preventDefault();e.stopImmediatePropagation();const {qol:action,id}=b.dataset;
 if(action==='edit-template')qol.editTemplate(id);if(action==='new-template')qol.editTemplate();if(action==='capture-template')qol.useTemplate(id,$('#capture-title')?.value.trim()||'');if(action==='capture')qol.capture();if(action==='switcher')qol.switcher();if(action==='bulk-edit')qol.bulkEdit();if(action==='templates')qol.templates();if(action==='save-template')qol.saveTemplate(id);if(action==='use-template')qol.useTemplate(id);if(action==='recovery')qol.recovery();if(action==='restore-task')qol.restore(id);if(action==='restore-backup')qol.restore(id,true);if(action==='follow-up')qol.followUp(id);
 if(action==='delete-template'&&confirm('Delete this template? Existing tasks stay unchanged.')){host.mutate(()=>host.state().templates=host.state().templates.filter(t=>t.id!==id),'Template deleted');qol.templates();}
 if(action==='acknowledge')host.mutate(()=>{const t=host.task(id);t.readyAcknowledged=qol.signature(t);},'Ready task acknowledged');
 if(action==='dismiss-reminder')host.mutate(()=>{const t=host.task(id);t.reminder='';t.remindedAt='';},'Reminder dismissed');
},true);
document.addEventListener('keydown',e=>{if(!host||!(e.ctrlKey||e.metaKey))return;if(e.key.toLowerCase()==='k'||e.shiftKey&&e.key.toLowerCase()==='n'){e.preventDefault();e.stopImmediatePropagation();if(e.key.toLowerCase()==='k')qol.switcher();else qol.capture();}},true);
