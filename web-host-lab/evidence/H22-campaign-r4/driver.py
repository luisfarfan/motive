import json,subprocess,sys,time
from pathlib import Path
lab=Path(__file__).resolve().parents[2];root=Path(__file__).resolve().parent
lock=Path('/Users/luisfarfan/Developer/products/motive/var/run/physical-test.lock')
start=time.monotonic();deadline=start+7200
print('WAITING_FOR_CANONICAL_PHYSICAL_SLOT; no native process launched',flush=True)
while lock.exists():
 if time.monotonic()>=deadline:
  (root/'waiting.json').write_text(json.dumps({'status':'WAIT_DEADLINE','waited_seconds':time.monotonic()-start,'native_launched':False},indent=2)+'\n')
  raise SystemExit(75)
 time.sleep(10)
(root/'waiting.json').write_text(json.dumps({'status':'SLOT_OBSERVED_ABSENT','waited_seconds':time.monotonic()-start,'native_launched':False,'note':'Trial must still acquire atomically.'},indent=2)+'\n')
stages=[('widgets-continuation','widgets','H22-widgets-r4',300000,17),('lifecycle','lifecycle','H22-lifecycle-r2',400000,0),('soak','soak','H22-soak-r2',500000,0)]
results=[]
for stage,suite,name,generation,index in stages:
 command=[sys.executable,str(lab/'tools/h22_suite.py'),'--suite',suite,'--name',name,'--generation',str(generation),'--start-index',str(index),'--continue-performance-failures']
 with (root/(stage+'.log')).open('x') as log:code=subprocess.call(command,stdout=log,stderr=subprocess.STDOUT)
 p=lab/'evidence'/name/'summary.json';summary=json.loads(p.read_text()) if p.exists() else {}
 plan=lab/'evidence'/name/'plan.json';expected=len(json.loads(plan.read_text())['cases']) if plan.exists() else 0
 proceed=bool(expected and len(summary.get('cases',[]))==expected and all(x['status']=='PASS' or x.get('continued_after_performance_failure') for x in summary.get('cases',[])))
 results.append({'stage':stage,'name':name,'returncode':code,'all_cases_executed_with_safety_gates':proceed})
 (root/'summary.json').write_text(json.dumps(results,indent=2)+'\n');print(stage,code,proceed,flush=True)
 if not proceed:raise SystemExit(code or 1)
