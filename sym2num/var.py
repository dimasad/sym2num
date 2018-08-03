"""Symbolic variables for code generation."""


import collections
import inspect
import keyword

import jinja2
import numpy as np
import sympy

from . import utils


class Variable:
    """Represents a code generation variable."""
    
    def print_prepare_validate(self, printer):
        """Returns code to validate and prepare the variable from arguments."""
        return ''
    
    @property
    def broadcast_elements(self):
        """List of elements which should be broadcast to generate the output."""
        return []

    def subs_dict(self, value):
        """Dictionary of substitutions to evaluate with a given value."""
        return {self: value}


class SymbolArray(Variable, sympy.Array):
    """Represents array of symbols for code generation."""
    
    def __new__(cls, name, array_like=None, dtype='float64'):
        if array_like is None:
            array_like = name
        
        elements, shape = elements_and_shape(array_like)
        if all(isstr(e) for e in elements):
            elements = [sympy.Symbol(n) for n in elements]
        
        if len(set(elements)) != len(elements):
            raise ValueError("elements of SymbolArray must be unique")
        
        obj = super().__new__(cls, elements, shape)
        return obj
    
    def __init__(self, name, array_like=None, dtype='float64'):
        if not isinstance(name, str):
            raise TypeError("expected str, but got {!r}".format(type(name)))
        if not isidentifier(name):
            raise ValueError(
                "'{}' is not a valid python identifier".format(name)
            )
        self.name = name
        """Variable name"""
        
        self.dtype = dtype
        """Generated array dtype."""

        symbol_names = set(symbol.name for symbol in self)
        if len(self) > len(symbol_names):
            raise ValueError("symbol names in array must be unique")
        
        if self.rank() > 0 and self.name in symbol_names:
            raise ValueError("positive-rank array name and symbols must differ")
    
    def ndenumerate(self):
        for ind in np.ndindex(*self.shape):
            yield ind, self[ind]
    
    def __len__(self):
        """Overrides `sympy.Array.__len__` which fails for rank-0 Arrays"""
        if self.shape == ():
            return 1
        else:
            return super().__len__()
    
    @property
    def broadcast_elements(self):
        """List of elements which should be broadcast to generate the output."""
        return [self[(0,) * self.rank()]]
    
    def subs_dict(self, value):
        value_array = sympy.Array(value)
        if self.shape != value_array.shape:
            msg = "Invalid shape for argument, expected {} and got {}"
            raise ValueError(msg.format(self.shape, value_array.shape))
        
        subs = {}
        for i in np.ndindex(*self.shape):
            subs[self[i]] = value_array[i]
        return subs
    
    @utils.cached_class_property
    def prepare_validate_template(cls):
        return jinja2.Template(inspect.cleandoc("""
        {{v.name}} = {{np}}.asarray({{v.name}}, dtype={{np}}.{{v.dtype}})
        {% if v.rank() -%}
        if {{v.name}}.shape[-{{v.rank()}}:] != {{v.shape}}:
        {%- set expected %}(...,{{v.shape |join(",")}}){% endset %}
            msg = "invalid shape for {{v.name}}, expected {{expected}}, got {}"
            raise ValueError(msg.format({{v.name}}.shape))
        {% endif -%}
        {% if v.rank() != 0 or v.name != v[()].name -%}
        # unpack `{{v.name}}` array elements
        {% for ind, symb in v.ndenumerate() -%}
        {{symb}} = {{v.name}}[..., {{ ind | join(', ')}}]
        {% endfor %}
        {%- endif %}
        """))
    
    def print_prepare_validate(self, printer):
        """Construct variable from an array_like and check dimensions."""
        context = dict(v=self, np=printer.numpy_alias, printer=printer)
        return self.prepare_validate_template.render(context)

    @property
    def symbols(self):
        """Set of symbols defined by this variable."""
        return set(self)
    

def elements_and_shape(array_like):
    """Return flat list of elements and shape from array-like nested iterable.
    
    Based on `sympy.tensor.array.ndim_array.NDimArray._scan_iterable_shape`.
    """
    #Detect if we are at a scalar element
    if (isstr(array_like) or not isiterable(array_like)):
        return [array_like], ()
    
    #We have an iterable, apply self to its elements
    subelements, subshapes = zip(*[elements_and_shape(e) for e in array_like])
    
    #Check if all subelements have the same shape
    if len(set(subshapes)) != 1:
        raise ValueError("could not determine shape unambiguously")
    
    #Create outputs
    elements = []
    for subelement in subelements:
        elements.extend(subelement)
    shape = (len(subelements),) + subshapes[0]
    return elements, shape


def isstr(obj):
    """Return whether an object is instance of `str`."""
    return isinstance(obj, str)


def isiterable(obj):
    """Return whether an object is iterable."""
    return isinstance(obj, collections.Iterable)


def isidentifier(ident: str) -> bool:
    """Return whether a string is a valid python identifier."""
    
    if not isinstance(ident, str):
        raise TypeError("expected str, but got {!r}".format(type(ident)))
    if not ident.isidentifier():
        return False
    if keyword.iskeyword(ident):
        return False
    
    return True