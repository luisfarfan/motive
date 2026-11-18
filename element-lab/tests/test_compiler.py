import sys, tempfile, json, copy
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'sdk'))
from common import LAB,LabError,read_json,write_json
from compiler import compile_element,emit
from contracts import contract,config,estimate

class CompilerTests(unittest.TestCase):
    def fixture(self):return LAB/'tests/fixtures/minimal.element.json'
    def compile(self,doc,**kwargs):
        with tempfile.TemporaryDirectory(dir=LAB/'.scratch') as folder:
            path=Path(folder)/'element.json';write_json(path,doc)
            return compile_element(path,**kwargs)
    @classmethod
    def setUpClass(cls):(LAB/'.scratch').mkdir(exist_ok=True)
    def test_real_native_contract(self):
        b=compile_element(self.fixture())
        self.assertEqual(b.report['status'],'PASS');self.assertFalse(b.report['plan']['executable'])
        self.assertEqual(b.report['budget']['counts']['sources'],1)
    def test_cycles_missing_and_bad_native_value(self):
        for name,code in [('cycle','CYCLE'),('missing-node','REFERENCE'),('invalid-opacity','PACK_OPACITY')]:
            with self.subTest(name=name),self.assertRaises(LabError) as caught:
                compile_element(LAB/f'tests/fixtures/{name}.element.json')
            self.assertEqual(caught.exception.code,code)
    def test_native_unknown_field(self):
        d=read_json(self.fixture());d['nodes'][1]['native']['css']='x'
        with self.assertRaises(LabError) as e:self.compile(d)
        self.assertEqual(e.exception.code,'PACK_SCHEMA')
    def test_property_compile_and_export(self):
        d=read_json(self.fixture());d['properties']=[{'id':'accent','label':'Accent','value':{'type':'color','default':123},'bindings':[{'scope':'node','ref':'plate','field':'color'}],'export':'creatorpack_property'}]
        b=self.compile(d,values={'accent':456})
        self.assertEqual(b.pack['overlays'][0]['definition']['color'],456)
        self.assertEqual(b.pack['properties'][0]['value']['value'],456)
        for values in [{'accent':'red'},{'accent':True},{'accent':16777216},{'missing':12}]:
            with self.subTest(values=values),self.assertRaises(LabError):self.compile(d,values=values)
    def test_budget_occupied(self):
        b=compile_element(self.fixture())
        with self.assertRaises(LabError):estimate(b.pack,{'scenes':8,'sources':0,'layers':0,'texture_bytes':0,'video_sources':0})
    def test_unreachable_and_underbudget(self):
        d=read_json(self.fixture());d['nodes'].append({'id':'unused','name':'unused','type':'composed','children':['plate']})
        with self.assertRaises(LabError):self.compile(d)
        d=read_json(self.fixture());d['budget']['max_texture_bytes']=1
        with self.assertRaises(LabError):self.compile(d)
    def test_atomic_failure_and_determinism(self):
        a=compile_element(self.fixture());b=compile_element(self.fixture())
        self.assertEqual(a,b)
        with tempfile.TemporaryDirectory(dir=LAB/'.scratch') as folder:
            dest=Path(folder)/'output';emit(a,dest)
            self.assertEqual(read_json(dest/'manifest.json'),a.pack)
            with self.assertRaises(LabError):emit(a,dest)
    def test_wrong_widget_event(self):
        d=read_json(self.fixture());d['events']=[{'id':'start','event_kind':'manual.button_pressed','match':'start','description':'invalid','actions':[{'type':'countdown_start','source_id':'plate'}]}]
        with self.assertRaises(LabError) as e:self.compile(d)
        self.assertEqual(e.exception.code,'INVALID_OVERLAY_ACTION')
    def test_symbolic_reference_missing(self):
        d=read_json(self.fixture());d['events']=[{'id':'show','event_kind':'manual.button_pressed','match':'show','description':'invalid','actions':[{'type':'show_overlay','source_id':'missing'}]}]
        with self.assertRaises(LabError) as e:self.compile(d)
        self.assertEqual(e.exception.code,'ACTION_REFERENCE')

if __name__=='__main__':unittest.main()
