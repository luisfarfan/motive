import gzip
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from h22_partial_evidence import retain_partial

class PartialEvidenceTests(unittest.TestCase):
    def test_retains_actual_bytes_excludes_symlink_and_cache_without_claiming_pass(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);fixture=root/'fixture';fixture.mkdir();out=root/'out';out.mkdir()
            data=b'{"partial":true}\n';(fixture/'lifecycle.jsonl').write_bytes(data)
            (fixture/'pointer.json').symlink_to(fixture/'lifecycle.jsonl')
            (fixture/'cache').mkdir();(fixture/'cache/opaque.json').write_bytes(b'{}')
            retain_partial(fixture,out)
            manifest=json.loads((out/'partial-native-manifest.json').read_text())
            self.assertEqual(manifest['status'],'INCOMPLETE');self.assertEqual(len(manifest['files']),1)
            row=manifest['files'][0];self.assertEqual(gzip.decompress((out/row['saved']).read_bytes()),data)
            self.assertEqual(row['sha256'],hashlib.sha256(data).hexdigest())

if __name__=='__main__':unittest.main()
