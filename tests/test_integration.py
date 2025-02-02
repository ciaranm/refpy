import unittest

from pathlib import Path

from env import refpy
from refpy import run, InvalidProof, ParseError

class TestIntegration(unittest.TestCase):
    def run_single(self, formulaPath):
        proofPath = formulaPath.with_suffix(".proof")
        with formulaPath.open() as formula:
            with proofPath.open() as proof:
                run(formula, proof)

    def correct_proof(self, formulaPath):
        self.run_single(formulaPath)

    def incorrect_proof(self, formulaPath):
        try:
            self.run_single(formulaPath)
        except InvalidProof as e:
            pass
        else:
            self.fail("Proof should be invalid.")

    def parsing_failure(self, formulaPath):
        try:
            self.run_single(formulaPath)
        except ParseError as e:
            pass
        else:
            self.fail("Parsing should fail.")

def create(formulaPath, helper):
    def fun(self):
        helper(self, formulaPath)
    return fun

current = Path(__file__).parent

correct = current.glob("integration_tests/correct/**/*.opb")
for file in correct:
    method = create(file, TestIntegration.correct_proof)
    method.__name__ = "test_correct_%s"%(file.stem)
    setattr(TestIntegration, method.__name__, method)

incorrect = current.glob("integration_tests/incorrect/**/*.opb")
for file in incorrect:
    method = create(file, TestIntegration.incorrect_proof)
    method.__name__ = "test_incorrect_%s"%(file.stem)
    setattr(TestIntegration, method.__name__, method)

parsing_failure = current.glob("integration_tests/parsing_failure/**/*.opb")
for file in parsing_failure:
    method = create(file, TestIntegration.parsing_failure)
    method.__name__ = "test_fail_parsing_%s"%(file.stem)
    setattr(TestIntegration, method.__name__, method)



if __name__=="__main__":
    unittest.main()