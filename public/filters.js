export function tagTone(value){let hash=0;for(const c of value.toLowerCase())hash=(Math.imul(hash,31)+c.charCodeAt(0))>>>0;return 'tag-tone-'+(hash%8);}
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export function multiSelect(label,choices,selected,attribute){
  const values=Array.isArray(selected)?selected:[selected];
  return `<details class="multi-filter" data-multi="${esc(attribute)}"><summary>${esc(label)} <span>${values.length?values.length+' selected':'Any'}</span></summary><div class="multi-options" role="group" aria-label="${esc(label)}">${choices.map(([value,text])=>`<label><input type="checkbox" value="${esc(value)}" ${values.includes(value)?'checked':''}> ${esc(text)}</label>`).join('')||'<small>No choices yet.</small>'}<button type="button" data-multi-clear>Clear selection</button></div></details>`;
}
export function multiValues(element){return [...element.querySelectorAll('input:checked')].map(input=>input.value);}
export function inlineChoices(label,choices,selected,attribute){
  return `<fieldset class="inline-filter" data-multi="${esc(attribute)}"><legend>${esc(label)}</legend><div class="inline-filter-values">${choices.map(([value,text])=>`<label><input type="checkbox" value="${esc(value)}" ${selected.includes(value)?'checked':''}><span class="${attribute==='basic-tags'?tagTone(value):''}">${esc(text)}</span></label>`).join('')||'<small>No choices yet.</small>'}</div></fieldset>`;
}
document.addEventListener('click',e=>{
  const button=e.target.closest('[data-multi-clear]');if(!button)return;
  e.preventDefault();const root=button.closest('[data-multi]');root.querySelectorAll('input').forEach(input=>input.checked=false);
  root.dispatchEvent(new Event('change',{bubbles:true}));
});

document.addEventListener('change',event=>{
  const root=event.target.closest('[data-multi]');if(!root)return;
  const count=multiValues(root).length;
  const summary=root.querySelector('summary span');if(summary)summary.textContent=count?count+' selected':'Any';
});
document.addEventListener('click',event=>{
  document.querySelectorAll('.multi-filter[open]').forEach(menu=>{if(!menu.contains(event.target))menu.open=false;});
});
