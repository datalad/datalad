# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Various small nodes
"""

import inspect
from six import iteritems, string_types

from datalad.support.network import get_url_disposition_filename, get_url_straight_filename
from datalad.utils import updated
from ..pipeline import FinishPipeline

class Sink(object):
    """A rudimentary node to sink/collect all the data passed into it
    """

    # TODO: add argument for selection of fields of data to keep
    def __init__(self, keys=None, output=None):
        """
        Parameters
        ----------
        keys : list of str, optional
          List of keys to store.  If not specified -- entire dictionaries stored
        output : str, optional
          If specified, it will be the key in the yielded data to contain all sunk
          data
        """
        self.data = []
        self.keys = keys
        self.output = output

    def get_values(self, *keys):
        return [[d[k] for k in keys] for d in self.data]

    def __call__(self, data):
        # ??? for some reason didn't work when I made entire thing a list
        if self.keys:
            raise NotImplementedError("Jason will do it")
        else:
            self.data.append(data)
        if self.output:
            data = updated(data, {self.output: self.data})
        yield data

    def clean(self):
        """Clean out collected data"""
        self.data = []


class rename(object):
    """Rename some items (i.e. change keys) in data for subsequent nodes
    """
    def __init__(self, mapping):
        """

        Use OrderedDict when order of remapping matters
        """
        self.mapping = mapping

    def __call__(self, data):
        # TODO: unittest
        data = data.copy()
        for from_, to_ in self.mapping:
            if from_ in data:
                data[to_] = data.pop(from_)
        yield data


class assign(object):
    """Class node to provide assignment of items in data

    With "interpolate" it allows for

    """
    # TODO: may be allow values to be a callable taking data in, so almost like
    # a node, but not yielding and just returning some value based on the data?
    def __init__(self, assignments, interpolate=False):
        """

        Parameters
        ----------
        assignments: dict
          keys: values pairs
        interpolate: bool, optional
          Either interpolate provided values using data
        """
        assert(isinstance(assignments, dict))
        self.assignments = assignments
        self.interpolate = interpolate

    def __call__(self, data):
        data = data.copy()  # we need to operate on a copy
        for k, v in self.assignments.items():
            data[k] = v % data if self.interpolate else v
        yield data

#class prune(object):

def get_url_filename(data):
    yield updated(data, {'filename': get_url_straight_filename(data['url'])})

def get_disposition_filename(data):
    """For the URL request content filename disposition
    """
    yield updated(data, {'filename': get_url_disposition_filename(data['url'])})

class interrupt_if(object):
    """Interrupt further pipeline processing whenever obtained data matches provided value(s)"""

    def __init__(self, values):
        """

        Parameters
        ----------
        values: dict
          Key/value pairs to compare arrived data against.  Would raise
          FinishPipeline if all keys have matched target values
        """
        self.values = values

    def __call__(self, data):
        for k, v in iteritems(self.values):
            if not (k in data and v == data[k]):
                # do nothing and pass the data further
                yield data
                # and quit
                return
        raise FinishPipeline

class range_node(object):
    """A node yielding incrementing integers in a data item (output by default)

    Primarily for testing
    """
    def __init__(self, n, output='output'):
        self.n = n
        self.output = output

    def __call__(self, data={}):
        for i in range(self.n):
            yield updated(data, {self.output: i})

def _string_as_list(x):
    if isinstance(x, string_types):
        return [x]
    return x

def func_to_node(func, data_args=(), data_kwargs=(), kwargs={}, outputs=()):
    """Generate a node out of an arbitrary function

    If provided function returns a generator, each item returned separately

    Parameters
    ----------
    data_args: list or tuple, optional
      Names of keys in data values of which will be given to the func
    data_kwargs: list or tuple, optional
      Names of keys in data which will be given to the func as keyword arguments
    kwargs: dict, optional
      Additional keyword arguments to pass into the function
    outputs: str or list or tuple, optional
      Names of keys to store output of the function in
    """

    def func_node(data):
        kwargs_ = kwargs.copy()
        args_ = []
        for k in _string_as_list(data_args):
            args_.append(data[k])
        for k in _string_as_list(data_kwargs):
            kwargs_[k] = data[k]

        out = func(*args_, **kwargs_)

        if not inspect.isgenerator(out):
            # for uniform handling below
            out = [out]

        for return_value in out:
            if outputs:
                outputs_ = _string_as_list(outputs)
                # we need to place it into copy of data
                data_ = data.copy()
                if len(outputs_) > 1:
                    # we were requested to have multiple outputs,
                    # then function should have provided matching multiple values
                    assert(len(return_value) == len(outputs_))
                else:
                    return_value = [return_value]  # for uniformicity

                for k, v in zip(outputs_, return_value):
                    data_[k] = v
                yield data_
            else:
                # TODO: does it make sense to yield the same multiple times ever
                # if we don't modify it???
                yield data

    in_args = list(_string_as_list(data_args)) + list(_string_as_list(data_kwargs))
    func_node.__doc__ = """Function %s wrapped into a node

It expects %s keys to be provided in the data and output will be assigned to %s
keys in the output.%s
""" % (
        func.__name__ if hasattr(func, '__name__') else '',
        ', '.join(in_args) if in_args else "no",
        ', '.join(_string_as_list(outputs)) if outputs else "no",
        (' Additional keyword arguments: %s' % kwargs) if kwargs else ""
    )

    return func_node