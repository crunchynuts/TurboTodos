// Keep unchanged controls, focus and scroll containers alive between renders.
// All application listeners are delegated, so newly inserted nodes need no wiring.
let fragments=new Map(), nextFragments=new Map();
export function renderFragment(id,html,tag){
  nextFragments.set(id,html);
  const previous=fragments.get(id);
  const safe=id.replace(/[&"<>]/g,c=>({'&':'&amp;','"':'&quot;','<':'&lt;','>':'&gt;'}[c]));
  if(previous?.html===html&&previous.node.isConnected)return `<${tag} data-render-id="${safe}" data-render-reuse></${tag}>`;
  return html.replace(/^<(\w+)/,`<$1 data-render-id="${safe}"`);
}
function key(node) {
  if(node.nodeType!==1)return null;
  const attr=['data-render-id','data-multi','id','data-task','data-drop','data-bulk-select'];
  for(const name of attr)if(node.hasAttribute(name))return node.tagName+':'+name+':'+node.getAttribute(name);
  if(node.hasAttribute('data-inline'))return node.tagName+':inline:'+node.dataset.inline+':'+node.dataset.id;
  return null;
}
function compatible(a,b){return a.nodeType===b.nodeType&&a.nodeName===b.nodeName&&key(a)===key(b);}
function sync(old,next){
  if(next.nodeType===1&&next.hasAttribute('data-render-reuse'))return;
  if(old.isEqualNode(next))return;
  if(old.nodeType!==1){if(old.nodeValue!==next.nodeValue)old.nodeValue=next.nodeValue;return;}
  if(old.matches('.multi-filter')&&old.open)next.open=true;
  for(const attr of [...old.attributes])if(!next.hasAttribute(attr.name))old.removeAttribute(attr.name);
  for(const attr of next.attributes)if(old.getAttribute(attr.name)!==attr.value)old.setAttribute(attr.name,attr.value);
  reconcile(old,next);
  // Attributes do not update dirty native form controls: reconcile their values too.
  if(old instanceof HTMLInputElement){if(old.value!==next.value)old.value=next.value;if(old.checked!==next.checked)old.checked=next.checked;}
  if(old instanceof HTMLSelectElement&&old.value!==next.value)old.value=next.value;
}
function reconcile(root,next){
  const keyed=new Map([...root.childNodes].map(n=>[key(n),n]).filter(([k])=>k!==null));
  let cursor=root.firstChild;
  for(const desired of [...next.childNodes]){
    const id=key(desired);
    let current=id!==null?keyed.get(id):cursor&&compatible(cursor,desired)?cursor:null;
    if(current&&!compatible(current,desired))current=null;
    if(!current){root.insertBefore(desired,cursor);continue;}
    if(current!==cursor)root.insertBefore(current,cursor);
    sync(current,desired);cursor=current.nextSibling;
  }
  while(cursor){const next=cursor.nextSibling;cursor.remove();cursor=next;}
}
export function patchHTML(root,html){
  const template=document.createElement('template');template.innerHTML=html;
  reconcile(root,template.content);
  const retained=new Map();
  for(const node of root.querySelectorAll('[data-render-id]')){
    const id=node.dataset.renderId;
    retained.set(id,{node,html:nextFragments.get(id)});
  }
  fragments=retained;nextFragments=new Map();
}
