import sys,unittest,hashlib
from copy import deepcopy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'sdk'))
from common import LAB,REPO,LabError
from modular import load_pack,select,combine

class ModularTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tech=load_pack(REPO/'creator-experience/packs/creator-tech');cls.arena=load_pack(REPO/'creator-experience/packs/neon-arena')
    def test_selection_removes_orphans(self):
        b=select(self.tech,source_ids=['tech-lower-third'])
        self.assertEqual(len(b.pack['overlays']),1);self.assertEqual(len(b.assets),0)
        self.assertLess(len(b.pack['scenes']),6);self.assertTrue(b.report['selection']['removed_rules'])
    def test_shared_resource_closure(self):
        b=select(self.tech,scene_ids=['tech-starting','tech-brb'])
        ids=[r['id'] for r in b.pack['resources']];self.assertEqual(len(ids),len(set(ids)))
        self.assertEqual(len(b.assets),len(ids));self.assertLess(len(b.assets),2)
    def test_combined_minimal(self):
        b=combine([select(self.tech,scene_ids=['tech-starting']),select(self.arena,scene_ids=['arena-starting'])])
        self.assertEqual(len(b.pack['scenes']),2);self.assertLessEqual(len(b.pack['overlays']),16)
        self.assertTrue(all(not r['enabled'] for r in b.rules['rules']))
    def test_same_pack_collision_namespacing_and_asset_dedup(self):
        p=select(self.tech,scene_ids=['tech-starting']);b=combine([p,p])
        self.assertEqual(len({o['id'] for o in b.pack['overlays']}),len(b.pack['overlays']))
        self.assertEqual(len(b.assets),len(p.assets))
    def test_full_combination_rejected(self):
        with self.assertRaises(LabError):combine([self.tech,self.arena])
    def test_invalid_selection_rejected(self):
        for kwargs in [{'scene_ids':['absent']},{'source_ids':[]},{'scene_ids':['tech-starting'],'source_ids':['tech-lower-third']}]:
            with self.subTest(kwargs=kwargs),self.assertRaises(LabError):select(self.tech,**kwargs)
    def test_source_unchanged(self):
        before=self.tech.pack.copy();select(self.tech,scene_ids=['tech-starting']);self.assertEqual(before,self.tech.pack)
    def test_deterministic(self):
        a=select(self.tech,scene_ids=['tech-starting']);b=select(self.arena,scene_ids=['arena-starting'])
        self.assertEqual(combine([a,b]),combine([a,b]))
    def test_unbound_action_is_explicitly_removed_or_rejected(self):
        p=deepcopy(self.tech)
        target=p.rules['rules'][0];target['actions']=[{'type':'counter_increment','counter_id':'unbound','amount':1}]
        selected=select(p,scene_ids=['tech-starting'])
        removed=next(r for r in selected.report['selection']['removed_rules'] if r['id']==target['id'])
        self.assertEqual(removed['reason'],'unbound_action_semantics')
        with self.assertRaises(LabError) as error:combine([p])
        self.assertEqual(error.exception.code,'COMPOSE_ACTION')

if __name__=='__main__':unittest.main()
