'''Sympy printer for numeric code generation.'''


import re

import numpy as np
import sympy
from sympy import printing


class NumpyPrinter(printing.str.StrPrinter):
    '''Sympy printer for generating python code using numpy.'''
    
    printmethod = 'numpyrepr'
    
    def __init__(self, numpy="_numpy"):
        super().__init__()        
        self.numpy = numpy
        '''The module name of numpy.'''

    @property
    def modules(self):
        return (self.numpy,)

    @property
    def imports(self):
        return ('import numpy as {}'.format(self.numpy),)
    
    def _print_acos(self, expr):
        return '%s.arccos(%s)' % (self.numpy, self._print(expr.args[0]))

    def _print_asin(self, expr):
        return '%s.arcsin(%s)' % (self.numpy, self._print(expr.args[0]))

    def _print_atan(self, expr):
        return '%s.arctan(%s)' % (self.numpy, self._print(expr.args[0]))

    def _print_atan2(self, expr):
        return '%s.arctan2(%s)' % (self.numpy, self.stringify(expr.args, ', '))
        
    def _print_acosh(self, expr):
        return '%s.arccosh(%s)' % (self.numpy, self._print(expr.args[0]))

    def _print_asinh(self, expr):
        return '%s.arcsinh(%s)' % (self.numpy, self._print(expr.args[0]))

    def _print_atanh(self, expr):
        return '%s.arctanh(%s)' % (self.numpy, self._print(expr.args[0]))
    
    def _print_Function(self, expr):
        return '%s.%s' % (self.numpy, super()._print_Function(expr))
    
    def _print_Pi(self, expr):
        return '%s.pi' % (self.numpy,)
    
    def _print_Pow(self, expr):
        base, exponent = expr.args
        if exponent == 0.5:
            return '%s.sqrt(%s)' % (self.numpy, self._print(base))
        if exponent == -0.5:
            return '(1/%s.sqrt(%s))' % (self.numpy, self._print(base))
        if exponent == 1:
            return '(%s)' % self._print(base)
        else:
            return super()._print_Pow(expr)


class ScipyPrinter(NumpyPrinter):
    '''Sympy printer for generating python code using scipy.'''
    
    def __init__(self, scipy="_scipy", *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.scipy = scipy
        '''The module name of scipy.'''

    @property
    def modules(self):
        return super().modules + (self.scipy,)
    
    @property
    def imports(self):
        return super().imports + ('import scipy as {}'.format(self.scipy),)
    
    def _print_erf(self, expr):
        return '%s.special.erf(%s)' % (self.scipy, self._print(expr.args[0]))
    
    def _print_loggamma(self, expr):
        return '%s.special.gammaln(%s)' % (self.scipy,self._print(expr.args[0]))

