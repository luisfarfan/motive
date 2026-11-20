import json,subprocess,sys
from pathlib import Path
lab=Path(__file__).resolve().parents[2];root=Path(__file__).resolve().parent
results=[]
for stage,suite,name,generation,index in [('lifecycle-continuation','lifecycle','H22-lifecycle-r3',600000,2),('soak','soak','H22-soak-r2',700000,0)]:
 command=[sys.executable,str(lab/'tools/h22_suite.py'),'--suite',suite,'--name',name,'--generation',str(generation),'--start-index',str(index),'--continue-performance-failures']
 with (root/(stage+'.log')).open('x') as log:code=subprocess.call(command,stdout=log,stderr=subprocess.STDOUT)
 p=lab/'evidence'/name/'summary.json';summary=json.loads(p.read_text()) if p.exists() else {}
 plan=lab/'evidence'/name/'plan.json';expected=len(json.loads(plan.read_text())['cases']) if plan.exists() else 0
 proceed=bool(expected and len(summary.get('cases',[]))==expected and all(x['status']=='PASS' or x.get('continued_after_performance_failure') for x in summary.get('cases',[])))
 results.append({'stage':stage,'name':name,'returncode':code,'all_cases_executed_with_safety_gates':proceed})
 (root/'summary.json').write_text(json.dumps(results,indent=2)+'\n');print(stage,code,proceed,flush=True)
 if not proceed:raise SystemExit(code or 1)
