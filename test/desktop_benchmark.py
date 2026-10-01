"""Repeatable desktop rendering benchmark, using synthetic data only."""
import json
from pathlib import Path
import sys
import tempfile
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import webview
from desktop import DesktopAPI,build_html
from importing import apply_import
from storage import Store
folder=tempfile.TemporaryDirectory();path=Path(folder.name)/'tasks.sqlite';store=Store(path)
s=apply_import({'filename':'tasks.json','content':json.dumps([{'title':f'Task {i}','notes':'Useful notes with context and next steps. '*5,'due':f'2026-10-{i%28+1:02}','tags':['Work',f'Area {i%5}'],'status':['backlog','next','doing','done'][i%4]} for i in range(int(sys.argv[1]) if len(sys.argv)>1 else 500)])},store.read());store.save(s)
api=DesktopAPI(path)
html=build_html().replace('window.turboHasUnsavedChanges=', '''window.benchmark=()=>{
 const result={};save=()=>{};
 const measure=(name,fn)=>{const values=[];for(let i=0;i<5;i++){const start=performance.now();fn();document.body.offsetHeight;values.push(performance.now()-start);}result[name+'_first']=Math.round(values[0]*10)/10;values.sort((a,b)=>a-b);result[name]=Math.round(values[2]*10)/10;};
 measure('board_render',()=>{view='board';render();});
 measure('complete_task',()=>complete(state.tasks[0].id));
 measure('search',()=>{query=query?'':'Task 1';render();});query='';
 measure('grid_render',()=>{view='grid';render();});
 measure('timeline_render',()=>{view='timeline';render();});
 measure('open_details',()=>{openTask(state.tasks[0].id);closeOverlay(true);});
 return result;
};window.turboHasUnsavedChanges=''')
w=webview.create_window('TurboTodos performance test',html=html,js_api=api,hidden=True,width=1400,height=900);api._window=w
results=[]
def run():
 try:
  for _ in range(200):
   if w.evaluate_js('Boolean(window.benchmark)'):break
   time.sleep(.1)
  results.append(w.evaluate_js('window.benchmark()'))
 finally:
  print(json.dumps(results),flush=True);w.destroy()
webview.start(run,gui='edgechromium',http_server=False)
folder.cleanup()
