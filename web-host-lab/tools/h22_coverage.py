#!/usr/bin/env python3
"""Reconcile original closed plans with executions across continuation roots.

Original unexecuted plan rows remain in the matrix. This separate report maps
exactly one actual run to each predeclared case; no failed run can be replaced.
"""
import argparse
import hashlib
import json
from pathlib import Path
from h22_matrix import LAB


def coverage(matrix_path, original_roots):
    raw=matrix_path.read_bytes();matrix=json.loads(raw);expected={};plans={}
    for root in original_roots:
        p=root/'plan.json';data=p.read_bytes();plan=json.loads(data)
        plans[str(p.resolve().relative_to(LAB))]=hashlib.sha256(data).hexdigest()
        for name,build,scenario,count,seconds,width,height,intermittent in plan['cases']:
            key=(plan['suite'],name)
            if key in expected:raise ValueError('DUPLICATE_PLANNED_CASE')
            expected[key]={'build':build,'scenario':scenario,'instances':count,'seconds':seconds,'width':width,'height':height,'fps':30}
    actual={};unexecuted=[]
    for row in matrix['rows']:
        key=(row['suite'],row['case'])
        if key not in expected:raise ValueError('UNPLANNED_CASE')
        if any(row[field]!=value for field,value in expected[key].items()):raise ValueError('CONFIGURATION_MISMATCH')
        if 'native_status' not in row:unexecuted.append(row['path']);continue
        if key in actual:raise ValueError('DUPLICATE_EXECUTION_CANNOT_REPLACE_FAIL')
        actual[key]=row
    missing=[{'suite':key[0],'case':key[1]} for key in expected if key not in actual]
    groups={}
    for key,config in expected.items():
        group=(config['scenario'],config['instances'],config['seconds'],config['width'],config['height'])
        item=groups.setdefault(group,dict(config,planned=0,executed=0,functional_pass=0,performance_pass=0,network_pass=0,case_pass=0,runs=[]))
        item['planned']+=1
        if key in actual:
            row=actual[key];item['executed']+=1;item['runs'].append(row['path'])
            for field,source in [('functional_pass','functional'),('performance_pass','performance'),('network_pass','network_lab'),('case_pass','case_result')]:item[field]+=int(row.get(source)=='PASS')
    for item in groups.values():
        all_pass=item['executed']==item['functional_pass']==item['network_pass']==item['case_pass']==item['planned']
        item['result']='PASS' if all_pass else 'FAIL' if item['executed']==item['planned'] else 'INCOMPLETE'
        item['admits_72s_configuration']=bool(item['seconds']==72 and item['planned']==3 and all_pass and item['performance_pass']==3)
    return {'status':'PASS' if not missing else 'INCOMPLETE','scope':'execution coverage only; not H22 acceptance',
        'matrix':str(matrix_path.resolve().relative_to(LAB)),'matrix_sha256':hashlib.sha256(raw).hexdigest(),
        'original_plans_sha256':plans,'expected_cases':len(expected),'executed_cases':len(actual),'missing':missing,
        'unexecuted_original_or_continuation_paths':unexecuted,'groups':list(groups.values()),
        'checker_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--matrix',type=Path,required=True)
    p.add_argument('--original-roots',type=Path,nargs='+',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    r=coverage(a.matrix,a.original_roots)
    with a.output.open('x') as f:json.dump(r,f,indent=2);f.write('\n')
    print(json.dumps({k:r[k] for k in ('status','expected_cases','executed_cases','missing')}))
