import copy
import json
from pathlib import Path
import tempfile
import unittest
from desktop import DesktopAPI
from importing import apply_import, plan_import
from storage import Store, Conflict

class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path=Path(self.folder.name)/'tasks.sqlite'
        self.store=Store(self.path)
        self.state=self.store.save(apply_import({'filename':'tasks.json','content':'[{"title":"Parent"},{"title":"Child"}]'},self.store.read()))

    def test_trash_restart_restore_keeps_number_and_does_not_resurrect_links(self):
        s=self.state
        parent,child=s['tasks']
        child['parentId']=parent['id']
        child['dependencies']=[parent['id']]
        s=self.store.save(s)
        s['tasks']=[child];child['parentId']='';child['dependencies']=[]
        s=self.store.save(s)
        store=Store(self.path)
        self.assertEqual(len(store.recovery_list()['trash']),1)
        restored=store.recover({'version':s['version'],'id':parent['id']})
        self.assertEqual(restored['tasks'][-1]['number'],parent['number'])
        self.assertEqual(restored['tasks'][0]['parentId'],'')
        self.assertEqual(store.recovery_list()['trash'],[])
        with self.assertRaises(Conflict):store.recover({'version':s['version'],'id':parent['id']})

    def test_backup_rotation_restore_and_safety_snapshot(self):
        store=self.store;s=self.state
        for _ in range(33):store._backup(s,force=True)
        backups=store.recovery_list()['backups'];self.assertEqual(len(backups),30)
        s['tasks'][0]['title']='Changed';s=store.save(s)
        restored=store.recover({'version':s['version'],'backup':backups[0]['name']})
        self.assertEqual(restored['tasks'][0]['title'],'Parent')
        self.assertEqual(restored['tasks'][0]['number'],1)
        latest=store.recovery_list()['backups'][0]['name']
        safety=json.loads((self.path.parent/'tasks-backups'/latest).read_text())
        self.assertEqual(safety['tasks'][0]['title'],'Changed')
        with self.assertRaises(ValueError):store.recover({'version':restored['version'],'backup':'../outside.json'})

    def test_recovery_bridge_and_archived_project(self):
        s=self.state;s['projects']=[{'id':'project','name':'Project','color':'#112233','active':True}]
        s['tasks'][0]['project']='project';s=self.store.save(s)
        task=s['tasks'].pop(0);s['projects'][0]['active']=False;s=self.store.save(s)
        api=DesktopAPI(self.path)
        self.assertEqual(api.request('GET','/api/recovery')['status'],200)
        response=api.request('POST','/api/recovery',{'id':task['id'],'version':s['version']})
        self.assertEqual(response['status'],200)
        self.assertEqual(response['body']['tasks'][-1]['project'],'project')

    def test_waiting_import_validation_and_templates(self):
        payload={'filename':'tasks.json','content':'[{"title":"Waiting","waiting_on":"Alex","follow_up_date":"2026-10-15"}]'}
        s=self.store.save(apply_import(payload,self.state))
        self.assertEqual(s['tasks'][-1]['waitingOn'],'Alex')
        template=copy.deepcopy(s['tasks'][-1]);s['templates']=[{'id':'template','name':'Reusable','tasks':[template]}]
        s=self.store.save(s)
        invalid=copy.deepcopy(s);invalid['templates'][0]['tasks'][0]['dependencies']=['missing']
        with self.assertRaises(ValueError):self.store.save(invalid)
        invalid=copy.deepcopy(s);invalid['tasks'][0]['followUpDate']='bad'
        with self.assertRaises(ValueError):self.store.save(invalid)
        self.assertEqual(self.store.read(),s)
        payload['content']='[{"title":"Bad","follow_up_date":"no"}]'
        self.assertFalse(plan_import(payload,s)[0]['canImport'])

if __name__=='__main__':unittest.main()
