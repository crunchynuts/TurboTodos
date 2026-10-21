import { multiSelect, multiValues, inlineChoices } from './filters.js';
// Review, delegation, hierarchy and filter behavior shared by every view.
const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const day = date => `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`;
const today = () => day(new Date());
const plus = (date,n) => {const d=new Date(date+'T12:00:00');d.setDate(d.getDate()+n);return day(d);};
const options = (items,value) => items.map(([id,label])=>`<option value="${escape(id)}" ${String(value)===String(id)?'selected':''}>${escape(label)}</option>`).join('');
const split = value => value.split(',').map(s=>s.trim()).filter(Boolean);

export function taskProgress(task,children=[]){
  if(children.length){
    if(children.every(t=>t.status==='done'))return 'completed';
    return children.some(t=>t.status==='done'||t.status==='doing')?'partial':'not-started';
  }
  return task.status==='done'?'completed':task.status==='doing'?'partial':'not-started';
}

export function attentionReasons(t,lookup,now=today(),clock=new Date()) {
  if(['done','cancelled'].includes(t.status))return [];
  const reasons=[];
  if(t.due&&t.due<=now)reasons.push(t.due<now?'Overdue':'Due today');
  if(t.reviewDate&&t.reviewDate<=now)reasons.push('Review due');
  if(t.waitingOn&&t.followUpDate&&t.followUpDate<=now)reasons.push('Follow up with '+t.waitingOn);
  if(t.reminder&&new Date(t.reminder)<=clock)reasons.push('Reminder due');
  const signature=[...t.dependencies].sort().map(id=>id+':'+(lookup(id)?.completedAt||'done')).join('|');
  if(t.dependencies.length&&t.dependencies.every(id=>lookup(id)?.status==='done')&&t.readyAcknowledged!==signature)reasons.push('Dependencies cleared');
  return reasons;
}

export function matchesFilter(task,node,tasks,now=today()) {
  if (!node || !node.rules?.length && node.rules) return true;
  if (node.rules) return node.mode==='any' ? node.rules.some(r=>matchesFilter(task,r,tasks,now)) : node.rules.every(r=>matchesFilter(task,r,tasks,now));
  const {field,op,value=''}=node;
  if(Array.isArray(op))return !op.length||op.some(choice=>matchesFilter(task,{...node,op:choice},tasks,now));
  if(field==='attention')return Boolean(attentionReasons(task,id=>tasks.find(t=>t.id===id),now).length)===(op==='yes');
  const values=Array.isArray(value)?value:[value];
  if(field==='due'||field==='review') {
    const date=field==='due'?task.due:task.reviewDate;
    if(op==='none')return !date;
    if(!date)return false;
    if(op==='overdue')return date<now;
    if(op==='due')return date<=now;
    if(op==='today')return date===now;
    let end;
    if(op==='week') {const d=new Date(now+'T12:00:00');end=plus(now,6-(d.getDay()+6)%7);}
    else if(op==='month'){const d=new Date(now+'T12:00:00');end=day(new Date(d.getFullYear(),d.getMonth()+1,0));}
    else end=plus(now,Number(op)-1);
    return date<=end && (node.includeOverdue || date>=now);
  }
  if(field==='delegated')return op==='person'?!values.length||values.some(v=>(task.delegatedTo||'').trim().toLowerCase()===v.trim().toLowerCase()):Boolean(task.delegatedTo?.trim())===(op==='yes');
  if(field==='tags'){const tags=Array.isArray(value)?value:split(value);if(!tags.length)return true;return op==='all'?tags.every(t=>task.tags.includes(t)):op==='none'?tags.every(t=>!task.tags.includes(t)):tags.some(t=>task.tags.includes(t));}
  if(field==='blocked'){const blocked=task.dependencies.some(id=>tasks.find(t=>t.id===id)?.status!=='done');return blocked===(op==='yes');}
  if(field==='radar')return Boolean(task.onRadar)===(op==='yes');
  if(field==='progress')return taskProgress(task,tasks.filter(t=>t.parentId===task.id))===op;
  if(field==='parent')return Boolean(task.parentId)===(op==='sub');
  if(field==='status'&&['active','done'].includes(op))return op==='done'?task.status==='done':!['done','cancelled'].includes(task.status);
  return !values.length|| (op==='isNot'?!values.includes(task[field]):values.includes(task[field]));
}

const fields=[['attention','Needs attention'],['due','Deadline'],['review','Next review'],['delegated','Delegation'],['tags','Tags'],['status','Status'],['project','Project'],['priority','Priority'],['blocked','Dependencies blocked'],['radar','Keep on Radar'],['parent','Task level'],['progress','Task progress']];
const operations={
  attention:[['yes','Yes'],['no','No']],
  progress:[['not-started','Not started'],['partial','Partial'],['completed','Completed']],
  due:[['overdue','Overdue'],['today','Today'],['7','Next 7 days'],['14','Next 14 days'],['30','Next 30 days'],['week','This week (Monday–Sunday)'],['month','This calendar month'],['none','No deadline']],
  review:[['due','Review due / overdue'],['7','Next 7 days'],['14','Next 14 days'],['30','Next 30 days'],['none','No review date']],
  delegated:[['yes','Delegated'],['no','Not delegated'],['person','Delegated to']],
  tags:[['any','Has any of'],['all','Has all of'],['none','Has none of']],
  status:[['active','Incomplete'],['done','Complete'],['is','Is'],['isNot','Is not']],
  project:[['is','Is'],['isNot','Is not']],priority:[['is','Is'],['isNot','Is not']],
  blocked:[['yes','Blocked'],['no','Not blocked']],radar:[['yes','Yes'],['no','No']],parent:[['top','Top-level task'],['sub','Subtask']],
};
const blank=()=>({mode:'all',rules:[]});
let host, active=blank(), activeName='', draft, quick=[], expanded=new Set();

export const power={
  defaultProject(fallback=''){const s=host.state(),id=s.settings.defaultProject??fallback;return s.projects.some(p=>p.id===id&&p.active!==false)?id:'';},
  configure(value){host=value;},
  layout(){return {active,activeName,quick,expanded:[...expanded]};},
  restoreLayout(l){if(!l)return;active=l.active?.rules?l.active:blank();activeName=l.activeName||'';quick=Array.isArray(l.quick)?l.quick:[];expanded=new Set(l.expanded||[]);},
  reset(){active=blank();activeName='';quick=[];},
  match(t){return matchesFilter(t,active,host.state().tasks)&&matchesFilter(t,this.quickFilter(),host.state().tasks);},
  hasFilter(){return active.rules.length>0||quick.length>0;},
  attention(t){return attentionReasons(t,host.task);},
  progress(task){return taskProgress(task,this.children(task.id));},
  children(id){return host.children(id);},
  reviewDue(t){return !['done','cancelled'].includes(t.status)&&t.reviewDate&&t.reviewDate<=today();},
  radar(t){return !['done','cancelled'].includes(t.status)&&(t.onRadar||t.reviewDate||t.delegatedTo||t.due&&t.due<=plus(today(),29));},
  myDay(t){return !['done','cancelled'].includes(t.status)&&(this.reviewDue(t)||t.due&&t.due<=today()||!t.waitingOn&&!t.delegatedTo&&!t.onRadar&&!t.reviewDate&&t.status==='doing');},
  visible(tasks,respectCollapse=false){
    if(!respectCollapse&&(host.filtersActive()||this.hasFilter()))return tasks;
    const ids=new Set(tasks.map(t=>t.id));
    const children=new Map();for(const t of tasks){if(t.parentId){if(!children.has(t.parentId))children.set(t.parentId,[]);children.get(t.parentId).push(t);}}
    const top=tasks.filter(t=>!t.parentId||!ids.has(t.parentId));
    return top.flatMap(t=>[t,...(expanded.has(t.id)?children.get(t.id)||[]:[])]);
  },
  meta(t){
    const parent=host.task(t.parentId),children=this.children(t.id),done=children.filter(c=>c.status==='done').length;
    return host.extraMeta(t)+`<div class="power-meta">${parent?`<button type="button" class="parent-label" data-power="open" data-id="${parent.id}">↳ #${parent.number||'…'} · ${escape(parent.title)}</button>`:''}${t.delegatedTo?`<span>Delegated to <b>${escape(t.delegatedTo)}</b></span>`:''}${t.reviewDate?`<span class="${this.reviewDue(t)?'overdue':''}">Review ${escape(t.reviewDate)}</span>`:t.onRadar?'<span>On Radar</span>':''}${children.length?`<button type="button" class="text-button" data-power="expand" data-id="${t.id}" aria-expanded="${expanded.has(t.id)}">${expanded.has(t.id)?'▾':'▸'} ${done}/${children.length} subtasks complete${done===children.length&&t.status!=='done'?' · Ready to complete':''}</button>`:''}</div>`;
  },
  toolbar(){return `<div class="power-toolbar"><button class="button ${this.hasFilter()?'toggled':''}" data-power="filters">Advanced filters${activeName?' · '+escape(activeName):this.hasFilter()?' · '+active.rules.length+' conditions':''}</button>${this.hasFilter()?'<button class="text-button" data-power="clear">Clear date / advanced filters</button>':''}<span class="field-help">Rolling windows include today. Date choices combine with the other filters.</span></div>${inlineChoices('Quick dates',[['overdue','Overdue'],['7','Due in next 7 days'],['14','Due in next 14 days'],['30','Due in next 30 days'],['week','Due this week'],['month','Due this month'],['review','Reviews due'],['attention','Needs my attention']],quick,'quick-dates')}`;},
  savedNav(){return `<div class="side-label">SAVED VIEWS</div><nav>${(host.state().savedViews||[]).map(v=>`<button class="nav-item" data-power="load-view" data-id="${v.id}">${escape(v.name)}</button>`).join('')||'<small class="field-help">Save a filter to keep it here.</small>'}</nav>`;},
  taskFields(t){
    const children=this.children(t.id),parents=host.state().tasks.filter(p=>!p.parentId&&p.id!==t.id);
    return `<div class="detail-section"><h3>Waiting on</h3><div class="detail-fields"><label>Waiting on<input name="waitingOn" maxlength="200" value="${escape(t.waitingOn)}" placeholder="Person, team, or response"></label><label>Follow-up date<input name="followUpDate" type="date" value="${escape(t.followUpDate)}"></label></div><small class="field-help">Separate from delegation and the deadline. Follow-ups appear in Needs attention when due.</small>${t.waitingOn?`<button type="button" class="button" data-qol="follow-up" data-id="${t.id}">Followed up / record update</button>`:''}</div><div class="detail-section"><h3>Ownership & reviews</h3><div class="detail-fields"><label>Delegated to<input name="delegatedTo" maxlength="200" value="${escape(t.delegatedTo)}" list="delegates" placeholder="Person or team"></label><datalist id="delegates">${[...new Set(host.state().tasks.map(x=>x.delegatedTo).filter(Boolean))].map(n=>`<option value="${escape(n)}">`).join('')}</datalist><label>Next review<input name="reviewDate" type="date" value="${escape(t.reviewDate)}"></label><label>Review every (days)<input name="reviewEveryDays" type="number" min="0" max="3650" value="${t.reviewEveryDays||0}"></label><label><input name="onRadar" type="checkbox" ${t.onRadar?'checked':''}> Keep on Radar</label></div><small class="field-help">0 = no repeat. Reviewed schedules from today, without changing the deadline. Delegation never changes status.</small>${host.state().tasks.some(x=>x.id===t.id)?`<button type="button" class="button" data-power="review" data-id="${t.id}">Reviewed / add update</button>`:'<small class="field-help">Save the task first to record a review.</small>'}<details class="review-history"><summary>Review history (${t.reviewHistory?.length||0})</summary>${[...(t.reviewHistory||[])].reverse().map(e=>`<article><time>${escape(new Date(e.at).toLocaleString())}</time><p>${escape(e.note)||'Reviewed'}</p></article>`).join('')||'<p>No reviews recorded yet.</p>'}</details></div><div class="detail-section parent-section"><h3>Parent task</h3><label><span class="sr-only">Parent task</span><select name="parentId" ${children.length?'disabled':''}><option value="">None — top-level task</option>${options(parents.map(p=>[p.id,'#'+(p.number||'…')+' · '+p.title]),t.parentId)}</select></label><button type="button" class="button open-parent" id="open-parent" data-power="open" data-id="${escape(t.parentId||'')}" ${t.parentId?'':'hidden'}>↑ Open parent${t.parentId?' #'+(host.task(t.parentId)?.number||'…'):''}</button>${children.length?'<input type="hidden" name="parentId" value=""><small class="field-help">A task with subtasks cannot itself become a subtask.</small>':''}<small class="field-help">The task this one belongs to. Leave blank for a top-level task.</small></div><div class="detail-section subtasks-section"><h3>Subtasks <span class="selection-count">${children.filter(c=>c.status==='done').length}/${children.length} complete</span></h3>${!children.length?'<p class="field-help">No subtasks.</p>':''}${children.map(c=>`<button type="button" class="subtask-link" data-power="open" data-id="${c.id}">${c.status==='done'?'✓':'○'} ${escape(c.title)} <small>${escape(c.delegatedTo)}</small></button>`).join('')}${!t.parentId&&host.state().tasks.some(x=>x.id===t.id)?`<button type="button" class="button" data-power="add-subtask" data-id="${t.id}">+ Add subtask</button>`:''}<small class="field-help">${t.parentId?'This task is already a subtask. Only one level of subtasks is supported.':'Break this task into independently tracked pieces, each with its own dates and ownership. Use the checklist for smaller steps.'}</small></div>`;
  },
  readFields(f){return {waitingOn:(f.get('waitingOn')||'').trim(),followUpDate:f.get('followUpDate')||'',delegatedTo:f.get('delegatedTo').trim(),reviewDate:f.get('reviewDate'),reviewEveryDays:Number(f.get('reviewEveryDays')||0),onRadar:f.has('onRadar'),parentId:f.get('parentId')||''};},
  validateTask(t){const parent=host.task(t.parentId);if(t.parentId&&(!parent||parent.parentId||t.parentId===t.id||this.children(t.id).length))return 'Choose a top-level parent. Only one level of subtasks is supported.';return '';},
  confirmComplete(t){const left=this.children(t.id).filter(c=>c.status!=='done').length;return !left||confirm(`${left} subtask(s) are still incomplete. Complete this parent anyway? Subtasks will stay open.`);},
  review(id){
    if(!host.leave())return;
    const t=host.state().tasks.find(x=>x.id===id);if(!t)return;
    host.dialog('Review · '+t.title,`<label class="modal-label">Progress update<textarea name="note" maxlength="5000" rows="4" placeholder="7 of 12 completed; reminded the remaining five."></textarea></label><label class="modal-label">Next review<input name="date" type="date" value="${t.reviewEveryDays?plus(today(),t.reviewEveryDays):''}"></label><p class="field-help">Leave the date blank to clear the next review. This does not complete the task or change its deadline.</p>`,f=>{
      if((t.reviewHistory||[]).length>=1000){host.toast('Review history is full (1,000 updates).');return;}
      host.mutate(()=>{t.reviewHistory=[...(t.reviewHistory||[]),{at:new Date().toISOString(),note:f.get('note').trim()}];t.reviewDate=f.get('date');},'Review recorded');host.close(true);
    },'Reviewed');
  },
  quickFilter(){
    return {mode:'any',rules:quick.map(name=>name==='review'?{field:'review',op:'due'}:name==='attention'?{field:'attention',op:'yes'}:{field:'due',op:name})};
  },
  preset(name){quick=Array.isArray(name)?name:[name];host.render();},
  filters(){draft=quick.length?(active.rules.length?{mode:'all',rules:[structuredClone(active),this.quickFilter()]}:this.quickFilter()):structuredClone(active);this.drawFilter();},
  drawFilter(){
    const opened=[...document.querySelectorAll('.advanced-form details[open][data-multi]')].map(el=>el.dataset.multi);
    const groupHtml=(node,path='',depth=0)=>`<fieldset class="filter-group" data-path="${path}"><legend>Match <select data-filter-mode="${path}" aria-label="Match conditions">${options([['all','all conditions'],['any','any condition']],node.mode)}</select></legend>${node.rules.map((r,i)=>{const p=path?path+'.'+i:String(i);return `<div class="filter-entry">${r.rules?groupHtml(r,p,depth+1):ruleHtml(r,p)}<button type="button" class="text-button" data-filter-remove="${p}" aria-label="Remove condition">Remove</button></div>`;}).join('')}<button type="button" class="button small" data-filter-add="${path}">+ Condition</button> ${depth<2?`<button type="button" class="button small" data-filter-group="${path}">+ Group</button>`:''}</fieldset>`;
    const ruleHtml=(r,path)=>{
      let values=null;
      if(r.field==='project')values=[['','No project'],...host.state().projects.map(p=>[p.id,p.name])];
      if(r.field==='status'&&['is','isNot'].includes(r.op))values=host.state().columns.map(c=>[c.id,c.name]);
      if(r.field==='priority')values=['low','medium','high','urgent'].map(p=>[p,p]);
      if(r.field==='tags')values=host.state().tags.map(t=>[t,t]);
      const ops=Array.isArray(r.op)?r.op:[r.op];
      if(r.field==='delegated'&&ops.includes('person'))values=[...new Set(host.state().tasks.map(t=>t.delegatedTo).filter(Boolean))].map(p=>[p,p]);
      const selected=Array.isArray(r.value)?r.value:r.field==='tags'?split(r.value||''):[r.value??''];
      if(values)for(const value of selected)if(value&&!values.some(([id])=>id===value))values.push([value,value]);
      const input=values?multiSelect('Values',values,selected,'value:'+path):'';
      const operator=['project','priority','tags'].includes(r.field)||r.field==='status'&&['is','isNot'].includes(r.op)?`<select data-filter-op="${path}" aria-label="Filter operator">${options(operations[r.field],r.op)}</select>`:multiSelect('Matches',operations[r.field],ops,'ops:'+path);
      return `<div class="filter-rule"><select data-filter-field="${path}" aria-label="Filter field">${options(fields,r.field)}</select>${operator}${input}${['due','review'].includes(r.field)&&ops.some(op=>['7','14','30','week','month'].includes(op))?`<label><input type="checkbox" data-filter-overdue="${path}" ${r.includeOverdue?'checked':''}> Include overdue</label>`:''}</div>`;
    };
    host.dialog('Advanced filters',`<p class="field-help">Conditions combine with the current search and basic filters. Quick dates combine with other filters. Loading a saved view starts from All tasks. Next 7 days means today plus six days.</p>${groupHtml(draft)}<div class="filter-save"><label class="modal-label">Save this advanced filter as<input id="view-name" maxlength="100" value="${escape(activeName)}" placeholder="e.g. Upcoming delegated work"></label><button type="button" class="button" data-power="save-view">Save view</button>${activeName?'<button type="button" class="text-button danger" data-power="delete-view">Delete saved view</button>':''}</div>`,()=>{syncDraft();active=structuredClone(draft);activeName='';quick=[];host.close(true);host.render();},'Apply filters');
    document.querySelector('#modal-form').classList.add('advanced-form');
    document.querySelectorAll('.advanced-form details[data-multi]').forEach(el=>{if(opened.includes(el.dataset.multi))el.open=true;});
  },
};

function at(path){return path.split('.').filter(Boolean).reduce((n,i)=>n.rules[Number(i)],draft);}
function syncDraft(){
  document.querySelectorAll('[data-multi^="value:"]').forEach(el=>at(el.dataset.multi.slice(6)).value=multiValues(el));
  document.querySelectorAll('[data-filter-overdue]').forEach(el=>at(el.dataset.filterOverdue).includeOverdue=el.checked);
}
document.addEventListener('change',e=>{
  const el=e.target,d=el.dataset;
  if(el.name==='parentId'){
    const button=document.querySelector('#open-parent'),parent=host.task(el.value);
    if(button){button.hidden=!parent;button.dataset.id=parent?.id||'';button.textContent='↑ Open parent'+(parent?' #'+(parent.number||'…'):'');}
  }
  const multi=el.closest('[data-multi]');
  if(multi?.dataset.multi==='quick-dates'){power.preset(multiValues(multi));return;}
  if(multi?.dataset.multi.startsWith('ops:')){syncDraft();const rule=at(multi.dataset.multi.slice(4));const values=multiValues(multi);rule.op=values;
    if(rule.field==='status'&&values.some(v=>v==='is'||v==='isNot'))rule.op=values.includes('isNot')?'isNot':'is';
    power.drawFilter();return;
  }
  if(d.filterMode!==undefined)at(d.filterMode).mode=el.value;
  if(d.filterField!==undefined){syncDraft();const rule=at(d.filterField);rule.field=el.value;rule.op=el.value==='status'?'is':operations[el.value][0][0];rule.value=[];delete rule.includeOverdue;power.drawFilter();}
  if(d.filterOp!==undefined){syncDraft();const rule=at(d.filterOp);rule.op=el.value;if(rule.field==='status'&&['is','isNot'].includes(rule.op))rule.value=[];power.drawFilter();}
});
document.addEventListener('click',e=>{
  const b=e.target.closest('[data-power],[data-filter-add],[data-filter-group],[data-filter-remove]');if(!b)return;
  e.preventDefault();e.stopImmediatePropagation();const d=b.dataset;
  if(d.filterAdd!==undefined||d.filterGroup!==undefined){syncDraft();const node=at(d.filterAdd??d.filterGroup);if(node.rules.length>=20){host.toast('Use at most 20 conditions per group.');return;}node.rules.push(d.filterGroup!==undefined?blank():{field:'due',op:'7'});power.drawFilter();return;}
  if(d.filterRemove!==undefined){syncDraft();const path=d.filterRemove.split('.'),index=Number(path.pop());at(path.join('.')).rules.splice(index,1);power.drawFilter();return;}
  if(d.power==='filters')power.filters();
  if(d.power==='clear'){power.reset();host.render();}
  if(d.power==='expand'){expanded.has(d.id)?expanded.delete(d.id):expanded.add(d.id);host.render();}
  if(d.power==='open'){if(host.leave())host.open(d.id);}
  if(d.power==='review')power.review(d.id);
  if(d.power==='add-subtask'){if(!host.leave())return;const parent=host.state().tasks.find(t=>t.id===d.id);if(parent){expanded.add(parent.id);host.open(null,{parentId:parent.id,project:parent.project,tags:[...parent.tags]});}}
  if(d.power==='load-view'){const v=(host.state().savedViews||[]).find(v=>v.id===d.id);if(v){host.clearBase();active=structuredClone(v.filter);activeName=v.name;quick=[];host.render();}}
  if(d.power==='save-view'){
    syncDraft();const name=document.querySelector('#view-name').value.trim();if(!name){host.toast('Give this view a name.');return;}
    const views=host.state().savedViews||[],existing=views.find(v=>v.name===name);
    if(!existing&&views.length>=100){host.toast('Keep at most 100 saved views.');return;}
    if(existing&&!confirm('Replace the saved filter named '+name+'?'))return;
    host.mutate(()=>{host.state().savedViews=views;if(existing)existing.filter=structuredClone(draft);else views.push({id:host.uid(),name,filter:structuredClone(draft)});},'View saved');active=structuredClone(draft);activeName=name;quick=[];host.close(true);host.render();
  }
  if(d.power==='delete-view'){if(!confirm('Delete saved view '+activeName+'? Tasks will be kept.'))return;host.mutate(()=>host.state().savedViews=(host.state().savedViews||[]).filter(v=>v.name!==activeName),'Saved view deleted');activeName='';host.close(true);host.render();}
},true);
