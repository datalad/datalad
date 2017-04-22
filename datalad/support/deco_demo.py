from datalad.distribution.dataset import Dataset, datasetmethod
from functools import wraps
from wrapt import decorator
from inspect import getargspec


# the "classical" functools decorator:
def my_functools_decorator(func):

    @wraps(func)
    def new_func(*args, **kwargs):
        print "wrapped with functools"
        return func(*args, **kwargs)

    return new_func


# old-style decorated function:
@my_functools_decorator
def old_style_function(one, two, three=None):
    print "old_style_function"
    print "one: {}\ntwo: {}\nthree: {}".format(one, two, three)


# the replacement for wraps:
def my_wraps_replacement(to_be_wrapped):

    @decorator(adapter=to_be_wrapped)
    def inter(to_be_wrapper, instance, args, kwargs):
        return to_be_wrapper(*args, **kwargs)

    return inter


# new-style decorator (compare to my_functools_decorator):
def my_wrapt_decorator(func):

    @my_wraps_replacement(func)
    def new_func(*args, **kwargs):
        print "wrapped with wrapt"
        return func(*args, **kwargs)

    return new_func


# new-style decorated function:
@my_wrapt_decorator
def new_style_function(one, two, three=None):
    print "new_style_function"
    print "one: {}\ntwo: {}\nthree: {}".format(one, two, three)


# what we have:
class StatusQuo(object):

    @staticmethod
    @datasetmethod(name='command')
    def __call__(what, dataset=None, ever=None):
        print "__call__:"
        print "dataset: {}\nwhat: {}\never: {}".format(dataset, what, ever)


# additional decorator, using functools:
class FunctoolClass(object):

    @staticmethod
    @datasetmethod(name='command_functool')
    @my_functools_decorator
    def __call__(what, dataset=None, ever=None):
        print "__call__:"
        print "dataset: {}\nwhat: {}\never: {}".format(dataset, what, ever)


# additional decorator, using wrapt:
class WraptClass(object):

    @staticmethod
    @datasetmethod(name='command_wrapt')
    @my_wrapt_decorator
    def __call__(what, dataset=None, ever=None):
        print "__call__:"
        print "dataset: {}\nwhat: {}\never: {}".format(dataset, what, ever)


# Full scale adaption requires datasetmethod and optional_args
# to use the replacement, too:
def new_optional_args(decorator):
    """allows a decorator to take optional positional and keyword arguments.
        Assumes that taking a single, callable, positional argument means that
        it is decorating a function, i.e. something like this::

            @my_decorator
            def function(): pass

        Calls decorator with decorator(f, `*args`, `**kwargs`)"""

    @my_wraps_replacement(decorator)
    def wrapper(*args, **kwargs):
        def dec(f):
            return decorator(f, *args, **kwargs)

        is_decorating = not kwargs and len(args) == 1 and isinstance(args[0], collections.Callable)
        if is_decorating:
            f = args[0]
            args = []
            return dec(f)
        else:
            return dec

    return wrapper


@new_optional_args
def new_datasetmethod(f, name=None, dataset_argname='dataset'):
    """Decorator to bind functions to Dataset class.

    The decorated function is still directly callable and additionally serves
    as method `name` of class Dataset.  To achieve this, the first positional
    argument is redirected to original keyword argument 'dataset_argname'. All
    other arguments stay in order (and keep their names, of course). That
    means, that the signature of the bound function is name(self, a, b) if the
    original signature is name(a, dataset, b) for example.

    The decorator has no effect on the actual function decorated with it.
    """
    if not name:
        name = f.func_name if PY2 else f.__name__

    @my_wraps_replacement(f)
    def apply_func(*args, **kwargs):
        """Wrapper function to assign arguments of the bound function to
        original function.

        Note
        ----
        This wrapper is NOT returned by the decorator, but only used to bind
        the function `f` to the Dataset class.
        """
        kwargs = kwargs.copy()
        from inspect import getargspec
        orig_pos = getargspec(f).args

        # If bound function is used with wrong signature (especially by
        # explicitly passing a dataset, let's raise a proper exception instead
        # of a 'list index out of range', that is not very telling to the user.
        if len(args) > len(orig_pos) or dataset_argname in kwargs:
            raise TypeError("{0}() takes at most {1} arguments ({2} given):"
                            " {3}".format(name, len(orig_pos), len(args),
                                          ['self'] + [a for a in orig_pos
                                                      if a != dataset_argname]))
        kwargs[dataset_argname] = args[0]
        ds_index = orig_pos.index(dataset_argname)
        for i in range(1, len(args)):
            if i <= ds_index:
                kwargs[orig_pos[i-1]] = args[i]
            elif i > ds_index:
                kwargs[orig_pos[i]] = args[i]
        return f(**kwargs)


    setattr(Dataset, name, apply_func)
    # So we could post-hoc later adjust the documentation string which is assigned
    # within .api
    apply_func.__orig_func__ = f
    return f


class FullScaleClass(object):

    @staticmethod
    @new_datasetmethod(name='command_fullscale')
    @my_wrapt_decorator
    def __call__(what, dataset=None, ever=None):
        """fullscale docstring"""

        print "actual __call__ method:"
        print "dataset: {}\nwhat: {}\never: {}".format(dataset, what, ever)


print "Examine simple functions ..."
print "old function:"
print getargspec(old_style_function)
old_style_function(1, 2, 3)
print "new function:"
print getargspec(new_style_function)
new_style_function(1, 2, 3)


print "Examine decorated methods ..."
print "The  current state of things:"
print "old __call__ method:"
print getargspec(StatusQuo.__call__)
StatusQuo()("this", ever="ever")
print "old Dataset method:"
print getargspec(Dataset.command)
ds = Dataset("/does/not/matter")
ds.command("this", ever="ever")

print "using functools-style additional decorator:"
print "functools __call__ method:"
print getargspec(FunctoolClass.__call__)
StatusQuo()("this", ever="ever")
print "functools Dataset method:"
print getargspec(Dataset.command_functool)
ds = Dataset("/does/not/matter")
# doesn't even work:
try:
    ds.command_functool("this", ever="ever")
except Exception as e:
    print str(e)

print "using new-style additional decorator:"
print "wrapt __call__ method:"
print getargspec(WraptClass.__call__)
WraptClass()("this", ever="ever")
print "wrapt Dataset method:"
print getargspec(Dataset.command_wrapt)
ds = Dataset("/does/not/matter")
ds.command_wrapt("this", ever="ever")

print "full-scale additional decorator:"
print "full-scale __call__ method:"
print getargspec(FullScaleClass.__call__)
FullScaleClass()("this", ever="ever")
print "full-scale Dataset method:"
print getargspec(Dataset.command_fullscale)
ds = Dataset("/does/not/matter")
ds.command_fullscale("this", ever="ever")

