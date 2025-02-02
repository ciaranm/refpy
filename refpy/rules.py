from refpy.constraints import Inequality
from refpy.constraints import LazyInequality
from refpy.constraints import Term

import parsy

from refpy import InvalidProof

registered_rules = []
def register_rule(rule):
    registered_rules.append(rule)
    return rule

def fallback_on_error(parse):
    """
    Call the getParser() method of the class to get a
    proper error message from the parser.
    """
    def f(*args, **kwargs):
        try:
            return parse(*args, **kwargs)
        except ValueError as e:
            try:
                if len(args) >= 1:
                    cls = args[0]
                    args = args[1:]
                else:
                    cls = kwargs["cls"]
                    del kwargs["cls"]
                if len(args) >= 1:
                    line = args[0]
                    args = args[1:]
                else:
                    line = kwargs["line"]
                    del kwargs["cls"]

                cls.getParser(*args, **kwargs).parse(line)
            except parsy.ParseError as parseError:
                # the id is not supposed to be passed in line
                # so we need to fix the position
                parseError.index += len(cls.Id)
                raise parseError
            except AttributeError:
                raise e
            else:
                raise e

    return f

class Rule():
    @staticmethod
    def getParser():
        """
        Returns:
            A parser that creates this rule from the string following the Id
        """
        raise NotImplementedError()

    @classmethod
    def parse(cls, line):
        return cls.getParser().parse(line.rstrip())

    def compute(self, antecedents):
        """
        Performs the action of the rule, e.g. compute new constraints or perform
        checks on the current proof.

        Args:
            antecedents (list): Antecedents in the order given by antecedentIDs

        Returns:
            computed constraints or empty list
        """
        raise NotImplementedError()

    def numConstraints(self):
        """
        Returns:
            number of constraints that will be produced by this rule
        """
        raise NotImplementedError()

    def antecedentIDs(self):
        """
        Return a list of indices of used antecednts
        """
        raise NotImplementedError()

    def isGoal(self):
        return False

    def __str__(self):
        return type(self).__name__

class DummyRule(Rule):
    def compute(self, db):
        return [Inequality([], 0)]

    def numConstraints(self):
        return 1

    def antecedentIDs(self):
        return []



class EqualityCheckFailed(InvalidProof):
    def __init__(self, expected, got):
        self.expected = expected
        self.got = got

@register_rule
class ConstraintEquals(Rule):
    Id = "e"

    @staticmethod
    def getParser():
        space = parsy.regex(" +").desc("space")

        opb = space.optional() >> parsy.regex(r"opb") \
                >> space >> Inequality.getOPBParser(allowEq = False)
        cnf = space.optional() >> parsy.regex(r"cnf") \
                >> space >> Inequality.getCNFParser()

        constraintId = space.optional() >> parsy.regex(r"[+-]?[0-9]+ ") \
            .map(int).desc("constraintId")

        return parsy.seq(constraintId, opb | cnf).combine(ConstraintEquals.fromParsy)

    @staticmethod
    def fromParsy(constraintId, constraint):
        return ConstraintEquals(constraintId, constraint[0])

    def __init__(self, constraintId, constraint):
        self.constraintId = constraintId
        self.constraint = constraint

    def compute(self, antecedents):
        if self.constraint != antecedents[0]:
            raise EqualityCheckFailed(self.constraint, antecedents[0])

    def numConstraints(self):
        return 0

    def antecedentIDs(self):
        return [self.constraintId]

    def __eq__(self, other):
        return self.constraintId == other.constraintId \
            and self.constraint == other.constraint

    def isGoal(self):
        return True

class ContradictionCheckFailed(InvalidProof):
    pass

@register_rule
class IsContradiction(Rule):
    Id = "c"

    @staticmethod
    def getParser():
        space = parsy.regex(" +").desc("space")
        constraintId = space.optional() \
            >> parsy.regex(r"[+-]?[0-9]+") \
                .map(int).map(IsContradiction.fromParsy)
        zero  = parsy.regex("0").desc("0 to end number sequence")

        return constraintId << space << zero

    @staticmethod
    def fromParsy(constraintId):
        return IsContradiction(constraintId)

    @classmethod
    def parse(cls, line):
        values = line.strip().split()
        if len(values) != 2:
            raise ValueError()

        return cls(int(values[0]))

    def __init__(self, constraintId):
        self.constraintId = constraintId

    def compute(self, antecedents):
        if not antecedents[0].isContradiction():
            raise ContradictionCheckFailed()

    def numConstraints(self):
        return 0

    def antecedentIDs(self):
        return [self.constraintId]

    def __eq__(self, other):
        return self.constraintId == other.constraintId

    def isGoal(self):
        return True

@register_rule
class LinearCombination(Rule):
    Id = "a"

    @staticmethod
    def getParser(create = True):
        space = parsy.regex(" +").desc("space")
        factor = parsy.regex(r"[0-9]+").map(int).desc("factor")
        constraintId = parsy.regex(r"[1-9][0-9]*").map(int).desc("constraintId")
        zero  = parsy.regex("0").desc("0 to end number sequence")

        summand = parsy.seq(factor << space, constraintId << space).map(tuple)
        parser = space.optional() >> summand.many() << zero

        if create:
            return parser.map(LinearCombination.fromParsy)
        else:
            return parser

    @staticmethod
    def fromParsy(sequence):
        factors, antecedentIds = zip(*sequence)
        return LinearCombination(factors, antecedentIds)

    def __init__(self, factors, antecedentIds):
        assert len(factors) == len(antecedentIds)
        self.antecedentIds = antecedentIds
        self.factors = factors

    def compute(self, antecedents):
        result = Inequality()

        for factor, constraint in zip(self.factors, antecedents):
            result.addWithFactor(factor, constraint)

        return [result]

    def numConstraints(self):
        return 1

    def antecedentIDs(self):
        return self.antecedentIds

    def __eq__(self, other):
        print(self.antecedentIds)
        print(other.antecedentIds)
        return self.antecedentIds == other.antecedentIds

    def isGoal(self):
        return False

@register_rule
class Division(LinearCombination):
    Id = "d"

    @staticmethod
    def getParser():
        space = parsy.regex(" +").desc("space")
        divisor = parsy.regex(r"[1-9][0-9]*").map(int).desc("positive divisor")

        return parsy.seq(
                space.optional() >> divisor,
                LinearCombination.getParser(create = False)
            ).combine(Division.fromParsy)

    @staticmethod
    def fromParsy(divisor, sequence):
        factors, antecedentIds = zip(*sequence)
        return Division(divisor, factors, antecedentIds)

    def __init__(self, divisor, factors, antecedentIds):
        assert len(factors) == len(antecedentIds)
        super().__init__(factors, antecedentIds)
        self.divisor = divisor

    def compute(self, antecedents):
        constraint = super().compute(antecedents)[0]
        constraint.divide(self.divisor)
        return [constraint]

    def __eq__(self, other):
        return super().__eq__(other) and self.divisor == other.divisor

@register_rule
class Saturation(LinearCombination):
    Id = "s"

    @staticmethod
    def getParser():
        return LinearCombination.getParser(create = False).map(Saturation.fromParsy)

    @staticmethod
    def fromParsy(sequence):
        factors, antecedentIds = zip(*sequence)
        return Saturation(factors, antecedentIds)

    def compute(self, antecedents):
        constraint = super().compute(antecedents)[0]
        constraint.saturate()
        return [constraint]

@register_rule
class LoadLitteralAxioms(Rule):
    Id = "l"

    @staticmethod
    def getParser():
        return parsy.regex(r" *[1-9][0-9]*") \
                .map(int)\
                .map(LoadLitteralAxioms.fromParsy)\
                .desc("number of literals") << parsy.regex(r" 0")

    @staticmethod
    def fromParsy(numLiterals):
        return LoadLitteralAxioms(numLiterals)

    # @classmethod
    # def parse(cls, line):
    #     values = line.strip().split()
    #     if len(values) != 2:
    #         raise ValueError()

    #     return cls(int(values[0]))

    def __init__(self, numLiterals):
        self.numLiterals = numLiterals

    def compute(self, antecedents):
        result = list()
        for i in range(1, self.numLiterals + 1):
            result.append(Inequality([Term(1, i)], 0))
            result.append(Inequality([Term(1,-i)], 0))

        return result

    def numConstraints(self):
        return 2 * self.numLiterals

    def antecedentIDs(self):
        return []

@register_rule
class ReversePolishNotation(Rule):
    Id = "p"

    @staticmethod
    def getParser():
        stackSize = 0
        def check(thing):
            nonlocal stackSize

            if isinstance(thing, int):
                stackSize += 1
            elif thing in ["+", "*", "d"]:
                stackSize -= 1
            elif thing == "s":
                stackSize += 0

            if stackSize < 0:
                return parsy.fail("Trying to pop from empty stack in reverse polish notation.")
            else:
                return parsy.success(thing)

        def finalCheck(instructions):
            nonlocal stackSize

            failed = stackSize != 1
            stackSize = 0
            if failed:
                return parsy.fail("Non empty stack at end of polish notation")
            else:
                return parsy.success(ReversePolishNotation(instructions))

        space = parsy.regex(r" +").desc("space")
        number = parsy.regex(r"[0-9]+").map(int).desc("number")
        operator = parsy.regex(r"[+*ds]").desc("operator +,*,d,s")

        return (space.optional() >> (number | operator).bind(check)).many().bind(finalCheck) \
            << space << parsy.regex(r"0").desc("0 to terminate sequence").optional()


    @classmethod
    @fallback_on_error
    def parse(cls, line):
        def f(word):
            if word in ["+", "*", "d", "s"]:
                return word
            else:
                return int(word)

        sequence = list(map(f, line.strip().split()))
        if sequence[-1] == 0:
            sequence.pop()
        return cls(sequence)


    class AntecedentIterator():
        def __init__(self, instructions):
            self.instructions = iter(instructions)

        def __iter__(self):
            return self

        def __next__(self):
            while (True):
                current = next(self.instructions)
                if isinstance(current, int):
                    return current
                if current in ["*", "d"]:
                    # consume one more, remember that we swaped the right operand and operator
                    next(self.instructions)

    def __init__(self, instructions):
        for i, x in enumerate(instructions):
            # the last operand of multiplication and division always
            # needs to be a constant and not a constraint, so we (can) switch
            # positions, which makes it easier to distinguish constraints from
            # constants later on
            if x in ["*", "d"]:
                instructions[i] = instructions[i - 1]
                instructions[i - 1] = x

        self.instructions = instructions

    def compute(self, antecedents):
        stack = list()
        antecedentIt = iter(antecedents)

        it = iter(self.instructions)
        ins = next(it, None)
        while ins is not None:
            if isinstance(ins, int):
                stack.append(LazyInequality(next(antecedentIt)))
            elif ins == "+":
                second = stack.pop()
                first  = stack.pop()
                stack.append(first.addWithFactor(1, second))
            elif ins == "*":
                constraint = stack.pop()
                factor = next(it)
                stack.append(constraint.multiply(factor))
            elif ins == "d":
                constraint = stack.pop()
                divisor = next(it)
                stack.append(constraint.divide(divisor))
            elif ins == "s":
                constraint = stack.pop()
                stack.append(constraint.saturate())

            ins = next(it, None)

        assert len(stack) == 1
        stack[0].contract()
        return stack

    def numConstraints(self):
        return 1

    def antecedentIDs(self):
        return ReversePolishNotation.AntecedentIterator(self.instructions)

class LoadFormula(Rule):
    Id = "f"

    @staticmethod
    def getParser(formula):
        def f(numVars):
            if numVars is not None and len(formula) != numVars:
                return parsy.fail("Number of constraints does not match.")
            else:
                return parsy.success(LoadFormula(formula, numVars))


        return parsy.regex(r" *[1-9][0-9]*") \
                .map(int)\
                .desc("number of constraints")\
                .optional()\
                .bind(f)\
                << parsy.regex(r" 0") \

    @classmethod
    def parse(cls, line, formula):
        values = line.strip().split()
        if len(values) == 2:
            return cls(formula, int(values[0]))
        elif len(values) == 1:
            return cls(formula)
        else:
            raise ValueError()

    def __init__(self, formula, numVars = None):
        self.formula = formula

    def compute(self, antecedents):
        return self.formula

    def numConstraints(self):
        return len(self.formula)

    def antecedentIDs(self):
        return []


class LoadFormulaWrapper():
    def __init__(self, formula):
        self.formula = formula
        self.Id = LoadFormula.Id

    def getParser(self):
        if self.formula is None:
            # for memory efficincy reasons
            raise RuntimeError("Can not call load Formula twice.")

        result = LoadFormula.getParser(self.formula)
        self.formula = None
        return result

    @fallback_on_error
    def parse(self, line):
        return LoadFormula.parse(line, self.formula)