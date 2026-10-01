import base64
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from desktop import DesktopAPI, build_html


class DesktopTests(unittest.TestCase):
    def test_bridge_import_tags_conflict_and_persistence(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'tasks.sqlite'
            api=DesktopAPI(path)
            state=api.request('GET','/api/workspace')['body']
            payload={'filename':'tasks.json','content':json.dumps([{'title':'Generic task','tags':['Original']}]),'version':state['version']}
            preview=api.request('POST','/api/import/preview',payload)
            self.assertTrue(preview['body']['canImport'])
            state=api.request('POST','/api/import',payload)['body']
            tid=state['tasks'][0]['id']
            for mode in ('add','remove'):
                result=api.request('POST','/api/tags',{'version':state['version'],'ids':[tid],'tags':['Bulk'],'mode':mode})
                self.assertEqual(result['status'],200)
                state=result['body']
                self.assertEqual('Bulk' in state['tasks'][0]['tags'],mode=='add')
            self.assertEqual(state['tasks'][0]['tags'],['Original'])
            self.assertEqual(api.request('POST','/api/import',payload)['status'],409)
            self.assertEqual(DesktopAPI(path).request('GET','/api/workspace')['body'],state)
            self.assertEqual(api.request('POST','/api/tags',[])['status'],400)
            self.assertEqual(api.request('POST','/unknown',{})['status'],404)

    def test_native_export_and_cancel(self):
        with tempfile.TemporaryDirectory() as folder:
            api=DesktopAPI(Path(folder)/'tasks.sqlite')
            api._window=Mock()
            target=Path(folder)/'tasks.csv'
            api._window.create_file_dialog.return_value=[str(target)]
            self.assertTrue(api.save_file('tasks.csv',base64.b64encode(b'title\nExample\n').decode()))
            self.assertEqual(target.read_bytes(),b'title\nExample\n')
            api._window.create_file_dialog.return_value=None
            self.assertFalse(api.save_file('tasks.csv',''))
            with self.assertRaises(ValueError): api.save_file('bad.exe','')

    def test_in_memory_assets(self):
        html=build_html()
        self.assertIn('window.TURBO_DESKTOP=true',html)
        self.assertNotIn('src="/app.js"',html)
        self.assertNotIn('href="/style.css"',html)
        self.assertNotIn("import {",html)
        self.assertIn('data:image/svg+xml;base64,',html)


if __name__=='__main__': unittest.main()
