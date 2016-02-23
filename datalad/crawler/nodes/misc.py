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
import os
import re

from os.path import curdir, join as opj, split as ops
from six import iteritems, string_types

from datalad.support.network import get_url_disposition_filename, get_url_straight_filename
from datalad.utils import updated
from ..pipeline import FinishPipeline
from ..pipeline import xrun_pipeline
from ..pipeline import PIPELINE_TYPES
from ...utils import auto_repr
from ...utils import find_files as _find_files

from logging import getLogger
lgr = getLogger('datalad.crawler.nodes')

@auto_repr
class Sink(object):
    """A rudimentary node to sink/collect all the data passed into it
    """

    # TODO: add argument for selection of fields of data to keep
    def __init__(self, keys=None, output=None, ignore_prefixes=['datalad_']):
        """
        Parameters
        ----------
        keys : list of str, optional
          List of keys to store.  If not specified -- entire dictionaries stored
        output : str, optional
          If specified, it will be the key in the yielded data to contain all sunk
          data
        ignore_prefixes : list, optional
          Keys with which prefixes to ignore.  By default all 'datalad_' ignored
        """
        self.data = []
        self.keys = keys
        self.output = output
        self.ignore_prefixes = ignore_prefixes or []

    def get_values(self, *keys):
        return [[d[k] for k in keys] for d in self.data]

    def __call__(self, data):
        # ??? for some reason didn't work when I made entire thing a list
        if self.keys:
            raise NotImplementedError("Jason will do it")
        else:
            data_ = {k: v
                     for k, v in data.items()
                     if not any(k.startswith(p) for p in self.ignore_prefixes)}
            self.data.append(data_)
        if self.output:
            data = updated(data, {self.output: self.data})
        yield data

    def clean(self):
        """Clean out collected data"""
        self.data = []


@auto_repr
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

# TODO: test
@auto_repr
class sub(object):
    """Apply re.sub regular expression substitutions to specified items"""
    def __init__(self, subs):
        """

        Parameters
        ----------
        subs: dict of key -> dict of pattern -> replacement
        """
        self.subs = subs

    def __call__(self, data):
        data = data.copy()
        for key, subs in self.subs.items():
            for from_, to_ in subs.items():
                data[key] = re.sub(from_, to_, data[key])
        yield data

@auto_repr
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

class _act_if(object):
    """Base class for nodes which would act if input data matches specified values
    """
    def __init__(self, values, re=False, negate=False):
        """

        Parameters
        ----------
        values: dict
          Key/value pairs to compare arrived data against.  Would raise
          FinishPipeline if all keys have matched target values
        re: bool, optional
          If specified values to be treated as regular expression to be
          searched
        negate: bool, optional
          Reverses, so acts (skips, etc) if no match
        """
        self.values = values
        self.re = re
        self.negate = negate

    def __call__(self, data):
        comp = re.search if self.re else lambda x, y: x == y
        matched = True
        for k, v in iteritems(self.values):
            if not (k in data and comp(v, data[k])):
                # do nothing and pass the data further
                matched = False
                break

        if matched != self.negate:
            for v in self._act(data):
                yield v
        else:
            yield data

    def _act(self):
        raise NotImplementedError


@auto_repr
class interrupt_if(_act_if):
    """Interrupt further pipeline processing whenever obtained data matches provided value(s)"""

    def _act(self, data):
        raise FinishPipeline

@auto_repr
class skip_if(_act_if):
    """Skip (do not yield anything) further pipeline processing whenever obtained data matches provided value(s)"""

    def _act(self, data):
        return []  # nothing will be yielded etc


@auto_repr
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

def func_to_node(func, data_args=(), data_kwargs=(), kwargs={}, outputs=(), **orig_kwargs):
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
        kwargs_.update(orig_kwargs)
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

# TODO: come up with a generic function_to_node adapter
#   actually there is already func_to_node but it is not clear how it works on
#   generators... in this commit also added **orig_kwargs to it
@auto_repr
class find_files(object):
    """Find files matching a regular expression in a pre-specified directory

    By default in current directory
    """
    def __init__(self, regex, fail_if_none=False, dirs=False, topdir=curdir):
        """

        Parameters
        ----------
        regex: basestring
        topdir: basestring, optional
          Directory where to search
        dirs: bool, optional
          Either to match directories
        fail_if_none: bool, optional
          Fail if none file matched throughout the life-time of this object, i.e.
          counts through multiple runs (if any run had files matched -- it is ok
          to have no matched files on subsequent run)
        """
        self.regex = regex
        self.topdir = topdir
        self.dirs = dirs
        self.fail_if_none = fail_if_none
        self._total_count = 0

    def __call__(self, data):
        count = 0
        for fpath in _find_files(self.regex, dirs=self.dirs, topdir=self.topdir):
            lgr.log(5, "Found file %s" % fpath)
            count += 1
            path, filename = ops(fpath)
            yield updated(data, {'path': path, 'filename': filename})
        self._total_count += count
        if not self._total_count and self.fail_if_none:
            raise RuntimeError("We did not match any file using regex %r" % self.regex)


@auto_repr
class switch(object):
    """Helper node which would decide which sub-pipeline/node to execute based on values in data
    """

    def __init__(self, key, mapping, default=None, missing='raise'):
        """
        Parameters
        ----------
        key: str
        mapping: dict
        default: node or pipeline, optional
          node or pipeline to use if no mapping was found
        missing: ('raise', 'stop', 'skip'), optional
          If value is missing in the mapping or key is missing in data
          (yeah, not differentiating atm), and no default is provided:
          'raise' - would just raise KeyError, 'stop' - would not yield
          anything in effect stopping any down processing, 'skip' - would
          just yield input data
        """
        self.key = key
        self.mapping = mapping
        self.missing = missing
        self.default = default

    @property
    def missing(self):
        return self._missing

    @missing.setter
    def missing(self, value):
        assert(value in {'raise', 'skip', 'stop'})
        self._missing = value

    def __call__(self, data):
        # make decision which sub-pipeline
        try:
            pipeline = self.mapping[data[self.key]]
        except KeyError:
            if self.default is not None:
                pipeline = self.default
            elif self.missing == 'raise':
                raise
            elif self.missing == 'skip':
                yield data
                return
            elif self.missing == 'stop':
                return

        if not isinstance(pipeline, PIPELINE_TYPES):
            # it was a node, return its output
            gen = pipeline(data)
        else:
            gen = xrun_pipeline(pipeline, data)

        # run and yield each result
        for out in gen:
            yield out