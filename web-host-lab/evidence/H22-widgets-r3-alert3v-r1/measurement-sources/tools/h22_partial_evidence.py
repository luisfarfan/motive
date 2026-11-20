"""Retain bounded partial native outputs after external interruption, never PASS."""
import gzip
import hashlib
import json


def retain_partial(fixture,output):
    records=[];used=0;skipped=[]
    for path in sorted(fixture.rglob('*')):
        if not path.is_file() or path.is_symlink() or path.suffix not in ('.json','.jsonl','.bgra'):continue
        relative=path.relative_to(fixture)
        if 'cache' in relative.parts:continue
        size=path.stat().st_size
        if size>16*1024**2 or used+size>128*1024**2 or len(records)>=256:
            skipped.append(str(relative));continue
        data=path.read_bytes();used+=len(data)
        packed=gzip.compress(data,mtime=0);target=output/'partial-native'/(str(relative)+'.gz')
        target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('xb') as f:f.write(packed)
        records.append({'source':str(relative),'saved':str(target.relative_to(output)),
            'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'gzip_sha256':hashlib.sha256(packed).hexdigest()})
    result={'status':'INCOMPLETE','reason':'missing final manifest; no final accounting acceptance',
        'files':records,'skipped_due_to_bounds':skipped}
    with (output/'partial-native-manifest.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
