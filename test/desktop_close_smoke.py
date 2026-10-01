"""Exercise real WinForms closing events; confirmation decisions are scripted."""
from pathlib import Path
import sys
import threading
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import webview
from closing import CloseGuard

windows=[];closed=[];checks=[];approved=False
for name,dirty in [('dirty',True),('clean',False)]:
    window=webview.create_window('Close regression '+name,html='<script>window.turboHasUnsavedChanges=()=>'+str(dirty).lower()+';</script>',hidden=True)
    guard=CloseGuard(window);window.events.closing+=guard.on_closing
    event=threading.Event();window.events.closed+=event.set
    windows.append(window);closed.append(event)

def confirm(title,message):
    checks.append((title,message));return approved
windows[0].create_confirmation_dialog=confirm
failures=[]
def run():
    global approved
    try:
        for w in windows:
            for _ in range(100):
                if w.evaluate_js("typeof window.turboHasUnsavedChanges==='function'"):break
                time.sleep(.05)
            else:raise AssertionError('engine not ready')
        windows[0].destroy()
        for _ in range(100):
            if checks:break
            time.sleep(.02)
        assert checks and not closed[0].is_set(),'dirty close did not cancel'
        assert windows[0].evaluate_js('1+1')==2,'UI blocked after cancelled close'
        time.sleep(.05)
        approved=True;windows[0].destroy()
        assert closed[0].wait(3),'approved dirty window did not close'
        windows[1].destroy()
        assert closed[1].wait(3),'clean window did not close'
        print('PASS: native close cancellation, responsive UI, confirmed close, clean close',flush=True)
    except Exception as exc:
        failures.append(str(exc));print('FAIL: '+str(exc),flush=True)
        # A test failure must not leave hidden windows running.
        import os
        os._exit(1)
webview.start(run,gui='edgechromium',http_server=False)
if failures:raise SystemExit(1)
