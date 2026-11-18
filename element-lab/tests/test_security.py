import sys,unittest,tempfile,os,copy,hashlib,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'sdk'))
from common import LAB,LabError,read_bytes,read_json,write_json
from compiler import compile_element
from contracts import contract,check_asset,estimate,png_info
from templates import motif,create
from web_contract import validate_web
from packaging import verify_package
from catalog import validate_catalog

class BoundaryTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):(LAB/'.scratch').mkdir(exist_ok=True)
 def test_declared_path_gate(self):
  for path in ['../outside','/private-test','a//b','a/./b','a/../b','a\\b','a:b','a/..hidden','a/%2e%2e']:
   with self.subTest(path=path),self.assertRaises(LabError):read_bytes(LAB,path)
 def test_descriptor_symlink_hardlink_and_size(self):
  with tempfile.TemporaryDirectory(dir=LAB/'.scratch') as tmp:
   root=Path(tmp);(root/'own').write_bytes(b'owned');(root/'link').symlink_to(root/'own');(root/'nested').symlink_to(root,target_is_directory=True)
   for path in ['link','nested/own']:
    with self.subTest(path=path),self.assertRaises(LabError):read_bytes(root,path)
   with self.assertRaises(LabError):read_bytes(root,'own',2)
   os.link(root/'own',root/'hard')
   with self.assertRaises(LabError):read_bytes(root,'hard')
 def test_asset_hash_dimensions_and_crc(self):
  b=compile_element(LAB/'native-elements/countdown/element.json');r=b.pack['resources'][0];data=b.assets[r['file_name']]
  for changed,bytes_ in [(dict(r,bytes=1),data),(dict(r,width=47),data),(r,data[:-1]+b'x')]:
   with self.subTest(changed=changed),self.assertRaises(LabError):check_asset(changed,bytes_)
  with self.assertRaises(LabError):png_info(data[:-1]+b'x')
 def test_unimplemented_decoder_fails_closed(self):
  data=b'not video';r={'id':'v','kind':'video','file_name':'v.mp4','sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'width':10,'height':10,'duration_ms':100}
  with self.assertRaises(LabError) as e:check_asset(r,data)
  self.assertEqual(e.exception.code,'ASSET_DECODER_UNAVAILABLE')
 def test_native_global_limits(self):
  b=compile_element(LAB/'tests/fixtures/minimal.element.json')
  for key,occupied in [('scenes',8),('sources',16),('layers',32),('texture_bytes',256*1024**2)]:
   counts={'scenes':0,'sources':0,'layers':0,'texture_bytes':0,'video_sources':0};counts[key]=occupied
   with self.subTest(key=key),self.assertRaises(LabError):estimate(b.pack,counts)
 def test_source_primitive_stays_strict(self):
  b=compile_element(LAB/'tests/fixtures/minimal.element.json')
  for field,value in [('color',16777216),('width',0),('opacity',-1)]:
   p=copy.deepcopy(b.pack);p['overlays'][0]['definition'][field]=value
   with self.subTest(field=field),self.assertRaises(LabError):contract(p,b.rules)
 def test_web_contract_denies_permissions_and_path(self):
  original=read_json(LAB/'web-elements/goal-celebration/web-element.json')
  for mutate in [lambda m:m['permissions'].update(network=True),lambda m:m.update(schema_version=2),lambda m:m['assets'][0].update(path='../outside'),lambda m:m.update(shell='forbidden')]:
   with tempfile.TemporaryDirectory(dir=LAB/'.scratch') as tmp:
    root=Path(tmp);m=copy.deepcopy(original);mutate(m);write_json(root/'web-element.json',m)
    with self.assertRaises(LabError):validate_web(root)
 def test_runtime_copy_and_inventory(self):
  self.assertEqual(read_bytes(LAB,'web-elements/runtime-prototype/runtime.mjs'),read_bytes(LAB,'web-elements/goal-celebration/runtime.mjs'))
  _,report,_=validate_web(LAB/'web-elements/goal-celebration');self.assertEqual(report['status'],'PASS')
 def test_catalog_and_browser_download_integrity(self):
  self.assertEqual(len(validate_catalog(LAB/'marketplace-contract/catalog.json')['entries']),8)
  for file in ['goal-celebration.motivepack','goal-celebration.motiveweb']:
   self.assertEqual(verify_package(LAB/'evidence'/file)['status'],'PASS')
 def test_invalid_template_identity_has_no_output(self):
  with tempfile.TemporaryDirectory(dir=LAB/'.scratch') as tmp:
   target=Path(tmp)/'new'
   with self.assertRaises(LabError):create('lower-third',target,'../invalid')
   self.assertFalse(target.exists())
 def test_resource_license_not_silently_replaced(self):
  with tempfile.TemporaryDirectory(dir=LAB/'.scratch') as tmp:
   root=Path(tmp);source=create('lower-third',root/'element')
   doc=read_json(source);doc['resources'][0]['license']='CC-BY-4.0';write_json(source,doc)
   with self.assertRaises(LabError) as e:compile_element(source)
   self.assertEqual(e.exception.code,'RESOURCE_LICENSE')
 def test_real_show_control_event_admission(self):
  b=compile_element(LAB/'native-elements/goal-celebration/element.json');events=read_json(LAB/'tests/fixtures/goal-events.json')
  disarmed=contract(b.pack,b.rules,events)['rehearsal'];self.assertEqual(disarmed['jobs'],[])
  for r in b.rules['rules']:r['enabled']=True
  r=contract(b.pack,b.rules,events)['rehearsal'];self.assertEqual(len(r['jobs']),1);self.assertEqual(r['jobs'][0]['state'],'simulated');self.assertEqual(r['live_commands_sent'],0)
  events[0]['simulated']=False
  with self.assertRaises(LabError) as e:contract(b.pack,b.rules,events)
  self.assertEqual(e.exception.code,'SIMULATION_ONLY')

if __name__=='__main__':unittest.main()
