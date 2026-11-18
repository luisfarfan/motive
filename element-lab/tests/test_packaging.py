import sys,unittest,zipfile,stat,copy
from io import BytesIO
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'sdk'))
from common import LAB,LabError,loads,encode
from modular import load_pack
from packaging import package_bundle,package_web_bytes,verify_bytes,passive_svg

def rewrite(data,change):
 with zipfile.ZipFile(BytesIO(data)) as z:files={i.filename:(i,z.read(i)) for i in z.infolist()}
 change(files);out=BytesIO()
 with zipfile.ZipFile(out,'w') as z:
  for name,(i,data) in files.items():z.writestr(i,data)
 return out.getvalue()

class PackagingTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.b=load_pack(LAB/'packs/mixed-example');cls.native=package_bundle(cls.b);cls.web=package_web_bytes(LAB/'web-elements/goal-celebration')
 def test_reproducible_and_distinct_contracts(self):
  self.assertEqual(self.native,package_bundle(self.b));self.assertEqual(self.web,package_web_bytes(LAB/'web-elements/goal-celebration'))
  for data,kind in [(self.native,'declarative_pack'),(self.web,'web_element')]:
   report=verify_bytes(data);self.assertEqual(report['content_kind'],kind);self.assertFalse(report['installed']);self.assertFalse(report['creator_identity_verified'])
 def test_hash_tamper(self):
  def alter(files):
   info,data=files['manifest.json'];files['manifest.json']=(info,data.replace(b'Motive',b'Broken'))
  with self.assertRaises(LabError):verify_bytes(rewrite(self.native,alter))
 def test_extra_and_missing_files(self):
  for mutate in [lambda f:f.update({'extra.js':(zipfile.ZipInfo('extra.js'),b'alert(1)')}),lambda f:f.pop('LICENSE')]:
   with self.subTest(mutate=mutate),self.assertRaises(LabError):verify_bytes(rewrite(self.native,mutate))
 def test_traversal_case_collision_symlink_exec_and_zipbomb(self):
  for name,mode,compression in [('../escape',stat.S_IFREG|0o644,0),('LICENSE',stat.S_IFREG|0o644,0),('link',stat.S_IFLNK|0o777,0),('tool',stat.S_IFREG|0o755,0),('bomb',stat.S_IFREG|0o644,zipfile.ZIP_DEFLATED)]:
   def alter(files):
    actual='license' if name=='LICENSE' else name;i=zipfile.ZipInfo(actual);i.create_system=3;i.external_attr=mode<<16;i.compress_type=compression
    files[actual]=(i,b'x'*100000 if compression else b'controlled')
   with self.subTest(name=name),self.assertRaises(LabError):verify_bytes(rewrite(self.native,alter))
 def test_passive_svg(self):
  for bad in [b'<svg><script>bad()</script></svg>',b'<svg><image href="https://example.invalid/a"/></svg>',b'<svg><rect onload="bad()"/></svg>',b'<svg><rect fill="url(#a)url(https://example.invalid)"/></svg>']:
   with self.subTest(bad=bad),self.assertRaises(LabError):passive_svg(bad)
 def test_duplicate_checksums(self):
  def alter(files):
   i,data=files['checksums.json'];d=loads(data);d['files'].append(d['files'][0]);files['checksums.json']=(i,encode(d))
  with self.assertRaises(LabError):verify_bytes(rewrite(self.native,alter))

if __name__=='__main__':unittest.main()
