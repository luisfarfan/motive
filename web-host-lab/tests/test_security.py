import sys
sys.dont_write_bytecode = True
import json
import shutil
import tempfile
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'poc/browser-host'))
from asset_broker import AssetBroker

EXAMPLE = ROOT.parent/'element-lab/web-elements/goal-celebration'
class Security(unittest.TestCase):
    def setUp(self):
        (ROOT/'.cache').mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=ROOT/'.cache')
        self.package = Path(self.temp.name)/'package'
        shutil.copytree(EXAMPLE,self.package)
    def tearDown(self): self.temp.cleanup()
    def broker(self): return AssetBroker(self.package,1,1)
    def manifest(self,change):
        path=self.package/'web-element.json';d=json.loads(path.read_text());change(d);path.write_text(json.dumps(d))
    def test_goal_uses_existing_contract_and_exact_inventory(self):
        b=self.broker();self.assertTrue(b.request(b.entry));self.assertTrue(b.navigation(b.entry,initial=True,main_frame=True))
        self.assertFalse(b.navigation(b.entry,initial=False,main_frame=True));self.assertFalse(b.navigation(b.entry,initial=True,main_frame=False))
    def test_denies_all_noninventory_targets(self):
        b=self.broker()
        targets=['https://example.invalid/x','http://127.0.0.1:9/','http://[::1]/','http://10.0.0.1/','http://169.254.169.254/',
                 'file:///etc/passwd','data:text/html,x','blob:motive://i1-g1/x','ws://localhost/','motive://i2-g1/index.html',
                 'motive://i1-g0/index.html',b.entry+'?x=1',b.entry+'#x',b.origin+'/%2e%2e/private',b.origin+'/../private',
                 b.origin+'/index.html%00',b.origin+'/Index.html',b.origin+'/LICENSE',b.origin+'/web-element.json']
        for url in targets:
            with self.subTest(url=url):self.assertIsNone(b.request(url))
        self.assertIsNone(b.request(b.entry,'POST'))
    def test_snapshot_cannot_be_replaced_after_validation(self):
        b=self.broker();old=b.request(b.entry).data;(self.package/'index.html').write_text('changed')
        self.assertEqual(b.request(b.entry).data,old);b.close();self.assertIsNone(b.request(b.entry))
    def test_hash_and_bytes_tampering_rejected(self):
        (self.package/'index.html').write_text('tamper')
        with self.assertRaises(ValueError):self.broker()
    def test_leaf_symlink_and_directory_symlink_rejected(self):
        target=self.package/'index.html';target.unlink();target.symlink_to(EXAMPLE/'index.html')
        with self.assertRaises(ValueError):self.broker()
        target.unlink();shutil.copy(EXAMPLE/'index.html',target)
        (self.package/'linked').symlink_to(EXAMPLE,target_is_directory=True)
        self.manifest(lambda d:d['assets'][0].update(path='linked/index.html'))
        with self.assertRaises(ValueError):self.broker()
    def test_hardlink_and_nonregular_asset_rejected(self):
        import os
        f=self.package/'index.html';local=self.package/'hardlink-target';shutil.copy(f,local);f.unlink();os.link(local,f)
        try:
            with self.assertRaises(ValueError):self.broker()
        finally:f.unlink()
        os.mkfifo(f)
        with self.assertRaises(ValueError):self.broker()
    def test_path_escape_duplicate_and_permissions_rejected(self):
        for change in [lambda d:d['assets'][0].update(path='../index.html'),lambda d:d['assets'].append(d['assets'][0]),lambda d:d['permissions'].update(network=True)]:
            shutil.copy(EXAMPLE/'web-element.json',self.package/'web-element.json');self.manifest(change)
            with self.assertRaises(ValueError):self.broker()
    def test_package_cannot_authorize_native_execution(self):
        self.assertFalse(self.broker().third_party_execution_allowed())
    def test_literal_scan_is_not_the_security_boundary(self):
        # An obfuscated network attempt can pass the old authoring review. The
        # broker still only serves inventory, and native execution stays blocked.
        import hashlib
        f=self.package/'goal.mjs';f.write_text(f.read_text()+"\nvoid (() => 'ht'+'tps'+':/'+'/example.invalid');\n")
        data=f.read_bytes()
        self.manifest(lambda d:next(a for a in d['assets'] if a['path']=='goal.mjs').update(bytes=len(data),sha256=hashlib.sha256(data).hexdigest()))
        b=self.broker();self.assertIsNone(b.request('https://example.invalid'));self.assertFalse(b.third_party_execution_allowed())

if __name__ == '__main__': unittest.main()
