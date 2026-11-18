import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'sdk'))
from common import LAB
from templates import TEMPLATES
from compiler import compile_element
from modular import combine

class NativeElementsTests(unittest.TestCase):
    def test_each_template_and_variant(self):
        for name in TEMPLATES:
            for variant in ['warm','cool']:
                with self.subTest(name=name,variant=variant):
                    b=compile_element(LAB/'native-elements'/name/'element.json',variant=variant)
                    self.assertEqual(b.pack['id'],name)
                    self.assertEqual(b.report['status'],'PASS');self.assertEqual(len(b.assets),1)
                    self.assertEqual(len(b.pack['scenes']),1)
                    for s in b.pack['scenes']:
                        for l in s['layers']:
                            for orient,w,h in [('horizontal',960,540),('vertical',540,960)]:
                                t=l[orient];self.assertGreaterEqual(t['x'],0);self.assertGreaterEqual(t['y'],0)
                                self.assertLessEqual(t['x']+t['width'],w);self.assertLessEqual(t['y']+t['height'],h)
    def test_animation_property_changes_action_too(self):
        b=compile_element(LAB/'native-elements/lower-third/element.json',{'entry-duration':900})
        self.assertEqual(b.pack['animations'][0]['duration_ms'],900)
        self.assertEqual(b.rules['rules'][0]['actions'][0]['animation']['duration_ms'],900)
    def test_composed_independent_elements(self):
        b=combine([compile_element(LAB/'native-elements'/n/'element.json') for n in TEMPLATES],single_scene=True)
        self.assertEqual(b.report['budget']['counts']['scenes'],1)
        self.assertEqual(b.report['budget']['counts']['sources'],9)
        self.assertEqual(len({l['horizontal']['order'] for l in b.pack['scenes'][0]['layers']}),9)
        self.assertTrue(all(not r['enabled'] for r in b.rules['rules']))

if __name__=='__main__':unittest.main()
