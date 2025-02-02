from recordclass import structclass
import parsy

def copysign(a, b):
       if b >= 0:
               return abs(a)
       else:
               return -abs(a)

from refpy.parser import getOPBConstraintParser, getCNFConstraintParser

Term = structclass("Term","coefficient variable")

class AllBooleanUpperBound():
    """
    Stub that needs to be replaced if we want to start handeling
    integer constraitns.
    """
    def __getitem__(self, key):
        return 1

class LazyInequality():
    """
    Essentially the same interface as Inequality but postpones some
    of the operations.
    """

    def __init__(self, constraint):
        self.constraint = constraint
        self.operations = []
        self.degrees = []

    @property
    def terms(self):
        return map(self.applyTerm, self.constraint.terms)

    @property
    def degree(self):
        return self.apply(self.constraint.degree)

    def applyTerm(self, value):
        return Term(self.apply(value.coefficient), value.variable)

    def apply(self, value):
        for op, i in self.operations:
            if op == "s":
                value = min(self.degrees[i], value)
            elif op == "d":
                value = (value + i - 1) // i
            elif op == "*":
                value *= i
        return value

    def saturate(self):
        self.degrees.append(self.apply(self.constraint.degree))
        self.operations.append(("s",len(self.degrees) - 1))
        return self

    def divide(self, d):
        self.operations.append(("d",d))
        return self

    def multiply(self, f):
        self.operations.append(("*",f))
        return self

    def addWithFactor(self, factor, other):
        result = Inequality(self.terms, self.degree)
        return result.addWithFactor(factor, other)

    def contract(self):
        pass

    def __repr__(self):
        return str(Inequality(self.terms, self.degree))

class Inequality():
    """
    Constraint representing sum of terms greater or equal degree.
    Terms are stored in normalized form, i.e. negated literals but no
    negated coefficient. Variables are represented as ingtegers
    greater 0, the sign of the literal is stored in the sign of the
    integer representing the variable, i.e. x ~ 2 then not x ~ -2.

    For integers 0 <= x <= d the not x is defined as d - x. Note that
    a change in the upperbound invalidates the stored constraint.
    """

    @staticmethod
    def fromParsy(t):
        result = list()

        if isinstance(t, list):
            # we got a clause from getCNFParser
            result.append(Inequality([Term(1,l) for l in t], 1))
        else:
            # we got a tuple containing a constraint
            terms, eq, degree = t

            result.append(Inequality([Term(a,x) for a,x in terms], degree))
            if eq == "=":
                result.append(Inequality([Term(-a,x) for a,x in terms], -degree))

        return parsy.success(result)

    @staticmethod
    def getOPBParser(allowEq = True):
        return getOPBConstraintParser(allowEq = True).bind(Inequality.fromParsy)

    @staticmethod
    def getCNFParser():
        return getCNFConstraintParser().bind(Inequality.fromParsy)

    def __init__(self, terms = list(), degree = 0, variableUpperBounds = AllBooleanUpperBound()):
        self.degree = degree
        self.terms = list(terms)
        self.expanded = False
        self.variableUpperBounds = variableUpperBounds
        self.normalize()
        self._dict = None

    @property
    def dict(self):
        if self._dict is None:
            self._dict = {abs(x.variable): x for x in self.terms}
        return self._dict

    def contract(self):
        if self._dict is not None:
            self.terms = [x for x in self.dict.values() if x.coefficient != 0]
            self._dict = None

    def normalize(self):
        for term in self.terms:
            if term.coefficient < 0:
                term.variable = -term.variable
                term.coefficient = abs(term.coefficient)
                self.degree += self.variableUpperBounds[abs(term.variable)] * term.coefficient

        # self.terms.sort(key = lambda x: abs(x.variable))

    # @profile
    def addWithFactor(self, factor, other):
        self.degree += factor * other.degree

        otherTerms = map(lambda x: Term(factor * x.coefficient, x.variable), other.terms)

        for other in otherTerms:
            try:
                my = self.dict[abs(other.variable)]
            except KeyError:
                self.terms.append(Term(other.coefficient, other.variable))
                self.dict[abs(other.variable)] = self.terms[-1]
            else:
                if (abs(my.variable) == abs(other.variable)):
                    a = copysign(my.coefficient, my.variable)
                    b = copysign(other.coefficient, other.variable)
                    newCoefficient = a + b
                    newVariable = copysign(abs(my.variable), newCoefficient)
                    newCoefficient = abs(newCoefficient)
                    cancellation = max(0, max(my.coefficient, other.coefficient) - newCoefficient)
                    self.degree -= cancellation * self.variableUpperBounds[abs(my.variable)]

                    my.coefficient = newCoefficient
                    my.variable = newVariable

        return self

    def saturate(self):
        self.dict
        for term in self.terms:
            term.coefficient = min(
                term.coefficient,
                self.degree)
        return self

    def divide(self, d):
        for term in self.terms:
            term.coefficient = (term.coefficient + d - 1) // d
        self.degree = (self.degree + d - 1) // d
        return self

    def multiply(self, f):
        for term in self.terms:
            term.coefficient = term.coefficient * f
        self.degree = self.degree * f
        return self

    def isContradiction(self):
        slack = -self.degree
        for term in self.terms:
            slack += term.coefficient
        return slack < 0


    def __eq__(self, other):
        # note that terms is assumed to be soreted
        self.contract()
        other.contract()
        key = lambda x: abs(x.variable)
        return self.degree == other.degree \
            and sorted(self.terms, key = key) == sorted(other.terms, key = key)

    def __str__(self):
        def term2str(term):
            if term.variable < 0:
                return "%+i~x%i"%(term.coefficient, -term.variable)
            else:
                return "%+ix%i"%(term.coefficient, term.variable)

        return " ".join(
            map(term2str, self.terms)) + \
            " >= %i" % self.degree

    def __repr__(self):
        return str(self)