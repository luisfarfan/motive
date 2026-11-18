import sys,tempfile,subprocess,json
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'sdk'))
from common import LAB

class CLITests(unittest.TestCase):
    def run_cli(self,*args):
        return subprocess.run([sys.executable,str(LAB/'sdk/motive_elements.py'),*map(str,args)],capture_output=True,text=True)
    def test_workflow(self):
        with tempfile.TemporaryDirectory(dir=LAB/'.scratch') as temp:
            d=Path(temp);element=d/'sample';pack=d/'pack'
            for args in [('new',element,'--template','lower-third'),('validate',element,'--set','title="New name"'),('pack',element,'-o',pack),('preview',pack,'-o',d/'preview'),('inspect',pack)]:
                result=self.run_cli(*args);self.assertEqual(result.returncode,0,result.stderr)
                self.assertIsInstance(json.loads(result.stdout),dict)
            self.assertTrue((d/'preview/index.html').is_file())
    def test_structured_failure(self):
        result=self.run_cli('validate',LAB/'tests/fixtures/cycle.element.json')
        self.assertEqual(result.returncode,1);self.assertEqual(json.loads(result.stderr)['error']['code'],'CYCLE')
    def test_capabilities_static(self):
        result=self.run_cli('capabilities');self.assertEqual(result.returncode,0)
        self.assertFalse(json.loads(result.stdout)['production_connected'])

if __name__=='__main__':unittest.main()
