"""Symbolic model code generation.

Improvement ideas
-----------------
* Add compiled code to linecache so that tracebacks can be produced, like done
  in the `IPython.core.compilerop` module.

"""


import abc
import collections.abc
import inspect
import re
import types

import attrdict
import numpy as np
import jinja2
import sympy

from . import function, utils


class_template = '''\
class {{generated_name}}({{class_signature}}):
    """Generated code for symbolic model {{sym_name}}"""

    signatures = {{signatures}}
    """Model function signatures."""

    var_specs = {{specs}}
    """Specification of the model variables."""
    {% for name, value in sparse_inds.items() %}
    {{name}}_ind = {{value}}
    """Nonzero indices of `{{name}}`."""
    {% endfor -%}
    {% for function in functions %}
    @staticmethod
    {{ function | indent}}
    {% endfor -%}
'''


parametrized_call_template = '''\
def {fname}(self, {signature}):
    """Parametrized version of `{fname}`."""
    return self.call(_wrapped_function, {args})
'''


class SymbolicModel(metaclass=abc.ABCMeta):
    symbol_assumptions = {'real': True}

    def __init__(self):
        self._init_variables()
        self._init_functions()
        self._init_derivatives()
        self._init_sparse()
    
    def _init_variables(self):
        """Initialize the model variables."""
        assumptions = self.symbol_assumptions
        self.vars = {}
        self.var_specs = {}
        for var_name in self.var_names:
            specs = getattr(self, var_name)
            var = np.zeros(np.shape(specs), dtype=object)
            for index, element_name in np.ndenumerate(specs):
                var[index] = sympy.Symbol(element_name, **assumptions)
            self.vars[var_name] = var
            self.var_specs[var_name] = specs
    
    def _init_functions(self):
        """Initialize the model functions."""
        self.functions = {}
        for fname in self.function_names:
            f = getattr(self, fname)
            if not callable(f):
                raise TypeError('Function `{}` not callable.'.format(fname))
            if isinstance(f, types.MethodType):
                argnames = inspect.getfullargspec(f).args[1:]
            else:
                argnames = inspect.getfullargspec(f).args
            args = [(name, self.vars[name]) for name in argnames]
            self.functions[fname] = function.SymbolicFunction(f, args)
    
    def _init_derivatives(self):
        """Initialize model derivatives."""
        for spec in getattr(self, 'derivatives', []):
            self.add_derivative(*spec)
    
    def _init_sparse(self):
        """Initialize the sparse functions."""
        self.sparse_inds = {}
        for spec in getattr(self, 'sparse', []):
            if isinstance(spec, str):
                fname = spec
                selector = lambda *inds: np.ones_like(inds[0], dtype=bool)
            else:
                fname, selector = spec
            f = self.functions[fname]
            inds = np.nonzero(f.out)
            inds = [ind[selector(*inds)] for ind in inds]
            fval = f.out[inds]
            fobj = function.SymbolicFunction(fval, f.args, fname + '_val')
            self.functions[fobj.name] = fobj
            self.sparse_inds[fname] = tuple(ind.tolist() for ind in inds)
    
    @property
    @abc.abstractmethod
    def var_names(self):
        """List of the model variable names."""
        raise NotImplementedError("Pure abstract method.")

    @property
    @abc.abstractmethod
    def function_names(self):
        """List of the model function names."""
        raise NotImplementedError("Pure abstract method.")
    
    @property
    def imports(self):
        meta = getattr(self, 'meta', None)
        if meta is None:
            return ()
        else:
            return ('import ' + meta.__module__,)
    
    @property
    def generated_name(self):
        """Name of generated class."""
        return type(self).__name__
    
    @property
    def class_signature(self):
        """Generated model class signature with metaclass definition."""
        meta = getattr(self, 'meta', None)
        if meta is None:
            return ''
        else:
            return 'metaclass={}.{}'.format(meta.__module__, meta.__qualname__)
    
    def pack(self, name, d={}, **kwargs):
        d = dict(d, **kwargs)
        var = self.vars[name]
        ret = np.zeros(var.shape, dtype=object)
        for index, elem in np.ndenumerate(var):
            try:
                ret[index] = d[elem.name]
            except KeyError:
                pass
        return ret
    
    def symbols(self, *args, **kwargs):
        symbol_list = utils.flat_cat(*args)
        symbols = attrdict.AttrDict({s.name: s for s in symbol_list})
        for argname, value in kwargs.items():
            var = self.vars[argname]
            for i, xi in np.ndenumerate(value):
                symbols[var[i].name] = xi
        return symbols
    
    def print_class(self, printer):
        tags = dict(
            generated_name=self.generated_name, 
            specs=self.var_specs, 
            sym_name=type(self).__name__,
            class_signature=self.class_signature,
            sparse_inds=self.sparse_inds,
        )
        tags['signatures'] = {name: list(f.args) 
                              for name, f in self.functions.items()}
        tags['functions'] = [fsym.print_def(printer)
                             for fsym in self.functions.values()]
        return jinja2.Template(class_template).render(tags)

    def print_module(self, printer):
        imports = '\n'.join(printer.imports + self.imports)
        class_code = self.print_class(printer)
        return '{}\n\n{}'.format(imports, class_code)
    
    def add_derivative(self, name, fname, wrt_names):
        if isinstance(wrt_names, str):
            wrt_names = (wrt_names,)
        
        f = self.functions[fname]
        for wrt_name in reversed(wrt_names):
            f = f.diff(self.vars[wrt_name], name)
        
        self.functions[name] = f


def class_obj(model, printer):
    code = model.print_module(printer)
    context = {}
    exec(code, context)
    return context[model.generated_name]


class ParametrizedModel:
    def __init__(self, params={}):
        # Save a copy of the given params
        self._params = {k: np.asarray(v) for k, v in params.items()}
        
        # Add default parameters for the empty variables
        for name, spec in self.var_specs.items():
            if np.size(spec) == 0 and name not in params:
                self._params[name] = np.array([])
    
    def parametrize(self, params={}, **kwparams):
        """Parametrize a new class instance with the given + current params."""
        new_params = self._params.copy()
        new_params.update(params)
        new_params.update(kwparams)
        return type(self)(new_params)
    
    def call_args(self, f, *args, **kwargs):
        fargs = self.signatures[f.__name__]
        call_args = {k: v for k, v in self._params.items() if k in fargs}
        call_args.update(filterout_none(kwargs))
        call_args.update(filterout_none(zip(fargs, args)))
        return call_args
    
    def call(self, f, *args, **kwargs):
        call_args = self.call_args(f, *args, **kwargs)
        return f(**call_args)
    
    @staticmethod
    def decorate(f):
        args = inspect.getfullargspec(f).args
        tags = {'fname': f.__name__, 
                'signature': ', '.join('%s=None' % a for a in args),
                'args': ', '.join(args)}
        context = dict(_wrapped_function=f)
        exec(parametrized_call_template.format(**tags), context)
        return context[f.__name__]
    
    @classmethod
    def meta(cls, name, bases, classdict):
        # Add ourselves to the bases
        if cls not in bases:
            bases = bases + (cls,)
        
        # Decorate the model functions
        for k, v in classdict.items():
            if isinstance(v, staticmethod):
                classdict[k] = cls.decorate(v.__func__)
        
        # Return the new class type
        return type(name, bases, classdict)

    @classmethod
    def pack(cls, name, d, fill=0):
        spec = np.array(cls.var_specs[name])
        fill = np.asarray(fill)
        ret = np.zeros(fill.shape + spec.shape)
        ret[...] = fill[(...,) + (None,) * spec.ndim]
        for index, elem_name in np.ndenumerate(spec):
            try:
                ret[(...,) + index] = d[elem_name]
            except KeyError:
                pass
        return ret


def filterout_none(d):
    """Returns a mapping without the values which are `None`."""
    items = d.items() if isinstance(d, collections.abc.Mapping) else d
    return {k: v for k, v in items if v is not None}

