import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'sdk'))
from common import LAB,LabError,loads,read_json,validate
from schemas import ELEMENT

class SchemaTests(unittest.TestCase):
    def test_versioned_fixture(self):
        validate(read_json(LAB/'tests/fixtures/minimal.element.json'),ELEMENT)
    def test_strict_negative_fixtures(self):
        for name in ['unknown-field','future-version']:
            with self.subTest(name=name), self.assertRaises(LabError):
                validate(read_json(LAB/f'tests/fixtures/{name}.element.json'),ELEMENT)
    def test_duplicate_keys_and_nan(self):
        for data in ['{"a":1,"a":2}','{"a":NaN}','{"a":Infinity}']:
            with self.subTest(data=data), self.assertRaises(LabError): loads(data)
    def test_boolean_not_number(self):
        with self.assertRaises(LabError): validate(True,{'type':'integer'})
    def test_both_orientations_required(self):
        x=read_json(LAB/'tests/fixtures/minimal.element.json');del x['layers'][0]['vertical']
        with self.assertRaises(LabError):validate(x,ELEMENT)

if __name__=='__main__':unittest.main()
