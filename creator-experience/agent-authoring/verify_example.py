#!/usr/bin/env python3
"""Verify generated authoring example against source hashes and real Rust contracts."""
from pathlib import Path
import hashlib, json, subprocess, tempfile, importlib.util
ROOT=Path(__file__).resolve().parent
CREATOR=ROOT.parent
REPO=CREATOR.parent
EXAMPLE=ROOT/'example'
EVIDENCE=EXAMPLE/'evidence'
EVIDENCE.mkdir(exist_ok=True)
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def save(name,data):(EVIDENCE/name).write_text(json.dumps(data,indent=2)+'\n')

def main():
 subprocess.run(['python3',str(ROOT/'generate_example.py')],check=True)
 generated=['brief.json','manifest.json','deck.json','rules.json','recipes.json','metadata.json','events.jsonl','LICENSE']+[f'previews/podcast-{scene}-{variant}.svg' for scene in ['live','brb'] for variant in ['horizontal','vertical']]
 with tempfile.TemporaryDirectory(prefix='regenerate-',dir=EVIDENCE) as temp:
  subprocess.run(['python3',str(ROOT/'generate_example.py'),'--output',temp],check=True,stdout=subprocess.DEVNULL)
  diffs=[name for name in generated if (EXAMPLE/name).read_bytes()!=(Path(temp)/name).read_bytes()]
  assert not diffs, diffs
 baseline=json.loads((ROOT/'capabilities-baseline.json').read_text());source_hashes=[]
 for source in baseline['sources']:
  actual=sha(REPO/source['path']);assert actual==source['sha256'],source['path'];source_hashes.append(dict(path=source['path'],sha256=actual,status='PASS'))
 pack=json.loads((EXAMPLE/'manifest.json').read_text());recipes=json.loads((EXAMPLE/'recipes.json').read_text())
 counts=dict(scenes=len(pack['scenes']),sources=len(pack['overlays']),layers=sum(len(s['layers']) for s in pack['scenes']))
 after=dict(scenes=counts['scenes'],sources=counts['sources']+recipes['sources_to_add'],layers=counts['layers']+recipes['layers_to_add'])
 assert after==recipes['project_after_selection']
 assert all(after[k]<=baseline['graph_limits'][k] for k in after)
 for scene in pack['scenes']:
  for orientation,(w,h) in [('horizontal',(960,540)),('vertical',(540,960))]:
   layouts=[l[orientation] for l in scene['layers']]+[s[orientation] for s in recipes['slots'] if s['scene_id']==scene['id']]
   assert len({l['order'] for l in layouts})==len(layouts)
   for l in layouts:assert 0<=l['x'] and 0<=l['y'] and l['x']+l['width']<=w and l['y']+l['height']<=h
 spec=importlib.util.spec_from_file_location('independent_asset_validation',CREATOR/'validation/validate.py');validator=importlib.util.module_from_spec(spec);spec.loader.exec_module(validator)
 preview_results=[dict(path=name,**validator.svg(EXAMPLE/name)) for name in generated if name.endswith('.svg')]
 estimate=validator.native_estimate(pack)
 result=subprocess.run(['cargo','run','--quiet','--locked','--offline','--manifest-path',str(CREATOR/'validation/Cargo.toml'),'--target-dir',str(CREATOR/'validation/target'),'--',str(EXAMPLE.relative_to(REPO))],cwd=REPO,text=True,capture_output=True)
 (EVIDENCE/'contracts.json').write_text(result.stdout)
 if result.returncode:raise RuntimeError(result.stderr or result.stdout)
 native=json.loads(result.stdout);assert native['status']=='PASS' and not native['production_connection']
 report=dict(status='PASS',example=pack['id'],mode='independent_authoring_validation',generated_files=len(generated),byte_identical_regeneration=True,source_baseline=source_hashes,counts_before_capture=counts,counts_after_explicit_user_camera_selection=after,scene_geometry_with_reserved_cameras='PASS',native_overlay_memory_estimate=estimate,previews=preview_results,contracts_report='contracts.json',contract_adversarial_cases=len(native['reports'][0]['adversarial_checks']),deck_buttons=len(native['reports'][0]['deck']),events=len(native['reports'][0]['events']),native_execution=False,live_commands_sent=0,not_verified=['Native install','Actual camera identities, permissions or capture','Native FreeType rendering','Live rule execution or scene output'])
 save('verification.json',report);print(json.dumps({k:report[k] for k in ['status','example','generated_files','byte_identical_regeneration','counts_before_capture','counts_after_explicit_user_camera_selection','contract_adversarial_cases','deck_buttons','events','live_commands_sent']}))
if __name__=='__main__':main()
