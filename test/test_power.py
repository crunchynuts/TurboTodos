import copy
import json
from pathlib import Path
import tempfile
import unittest
from importing import apply_import, plan_import
from storage import Store, initial_workspace, validate


class PowerFeaturesTests(unittest.TestCase):
    def setUp(self):
        self.state=apply_import({'filename':'tasks.json','content':json.dumps([{'title':'Course'},{'title':'Alex course'}])},initial_workspace())

    def test_legacy_fields_remain_optional(self):
        for task in self.state['tasks']:
            for key in ('delegatedTo','reviewDate','reviewEveryDays','onRadar','parentId','reviewHistory'):
                task.pop(key,None)
        self.assertEqual(validate(self.state),self.state)

    def test_hierarchy_validation(self):
        parent,child=self.state['tasks']
        child['parentId']=parent['id']
        validate(self.state)
        for invalid in ('missing',child['id']):
            child['parentId']=invalid
            with self.assertRaises(ValueError):validate(self.state)
        child['parentId']=parent['id'];parent['parentId']=child['id']
        with self.assertRaises(ValueError):validate(self.state)
        parent['parentId']=''
        third=copy.deepcopy(child);third['id']='third';third['parentId']=child['id'];self.state['tasks'].append(third)
        with self.assertRaises(ValueError):validate(self.state)

    def test_new_fields_and_saved_filters_persist(self):
        parent,child=self.state['tasks'];child['parentId']=parent['id'];child['delegatedTo']='Alex'
        parent.update(reviewDate='2026-10-15',reviewEveryDays=14,onRadar=True,reviewHistory=[{'at':'2026-10-01T12:00:00','note':'7 of 12 complete'}])
        self.state['savedViews']=[{'id':'attention','name':'Needs attention','filter':{'mode':'all','rules':[{'field':'status','op':'active'},{'mode':'any','rules':[{'field':'due','op':'overdue'},{'field':'review','op':'due'}]}]}}]
        with tempfile.TemporaryDirectory() as folder:
            store=Store(Path(folder)/'tasks.sqlite');saved=store.save(self.state)
            self.assertEqual(Store(store.path).read(),saved)
        for key,value in [('reviewDate','2026-02-30'),('reviewEveryDays',-1),('reviewEveryDays',True),('onRadar','yes'),('reviewHistory',[{'at':'','note':'bad'}])]:
            broken=copy.deepcopy(self.state);broken['tasks'][0][key]=value
            with self.assertRaises(ValueError):validate(broken)
        self.state['savedViews'][0]['filter']={'field':'due','op':'7'}
        with self.assertRaises(ValueError):validate(self.state)

    def test_multi_select_saved_filters(self):
        self.state['savedViews']=[{'id':'multi','name':'Multiple selections','filter':{'mode':'all','rules':[{'field':'due','op':['overdue','7']},{'field':'priority','op':'is','value':['high','urgent']},{'field':'tags','op':'all','value':['Work','Course']}]}}]
        validate(self.state)
        for op in ([['7']],['invalid'],[True]):
            broken=copy.deepcopy(self.state);broken['savedViews'][0]['filter']['rules'][0]['op']=op
            with self.assertRaises(ValueError):validate(broken)
        broken=copy.deepcopy(self.state);broken['savedViews'][0]['filter']['rules'][1]['value']=[4]
        with self.assertRaises(ValueError):validate(broken)

    def test_import_review_delegation_and_parent(self):
        payload={'filename':'tasks.json','content':json.dumps([{'title':'Subtask','parent_id':self.state['tasks'][0]['id'],'delegated_to':'Alex','review_date':'2026-10-15','review_every_days':14,'on_radar':True}])}
        summary,pending=plan_import(payload,self.state)
        self.assertTrue(summary['canImport']);self.assertEqual(pending[0]['delegatedTo'],'Alex')
        self.assertEqual(pending[0]['reviewEveryDays'],14)
        payload['content']=json.dumps([{'title':'Bad','parent_id':'missing'}])
        self.assertFalse(plan_import(payload,self.state)[0]['canImport'])


if __name__=='__main__':unittest.main()
