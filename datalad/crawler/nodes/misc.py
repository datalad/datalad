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
import stat
import pdb

from stat import ST_MODE, S_IEXEC, S_IXOTH, S_IXGRP
from os.path import curdir, isdir, isabs, exists, join as opj, split as ops
from six import iteritems, string_types

from datalad.support.network import get_url_disposition_filename, get_url_straight_filename
from datalad.utils import updated
from ..pipeline import FinishPipeline
from ..pipeline import xrun_pipeline
from ..pipeline import PIPELINE_TYPES
from ...utils import auto_repr
from ...utils import find_files as _find_files

from logging import getLogger
from nose.tools import eq_, assert_raises

lgr = getLogger('datalad.crawler.nodes')

@auto_repr
class fix_permissions(object):
    """A node used to check the permissions of a file and set the executable bit

    """

    def __init__(self, file_re='.*', executable=False, input='filename', path=None):
        """
            Parameters
            ----------
            file_re : str, optional
              Regular expression str to which the filename must contain (re.search)
            executable : boolean, optional
              If false, sets file to allow no one to execute. If true, sets file
              to be executable to those already allowed to read it
            input : str, optional
              Key which holds value that is the filename or absolute path in data
            path : str, optional
              If absolute path is not specifed in data, path must be expressed
              here

            """
        self.file_re = file_re
        self.executable = executable
        self.input = input
        self.path = path

    def __call__(self, data):
        filename = data.get(self.input)

        # check that file matches regex
        if not re.search(self.file_re, filename):
            yield data
            return  # early termination since nothing to do

        # check that absolute path exists
        if not isabs(filename):
            path = self.path or data.get('path')
            if path:
                filename = opj(path, filename)

        # check existance of file and that path is not a dir
        if exists(filename) and not isdir(filename):
            per = oct(os.stat(filename)[ST_MODE])[-3:]
            st = os.stat(filename)

            permissions = [S_IEXEC, S_IXGRP, S_IXOTH]

            if self.executable:
                # make is executable for those that can read it
                for i, scope in enumerate(permissions):
                    if per[i] == '6' or '4':
                        os.chmod(filename, st.st_mode | scope)
                        st = os.stat(filename)

            else:
                # strip everyone away from executing
                current = stat.S_IMODE(os.lstat(filename).st_mode)
                os.chmod(filename, current & ~S_IEXEC & ~S_IXGRP & ~S_IXOTH)

            nper = oct(os.stat(filename)[ST_MODE])[-3:]
            lgr.debug('Changing permissions for file %s from %s to %s', filename, per, nper)

        yield data


@auto_repr
class Sink(object):
    """A rudimentary node to sink/collect all the data passed into it
    """

    def __init__(self, keys=None, output=None, ignore_prefixes=['datalad_']):
        """
        Parameters
        ----------
        keys : list of str, optional
          List of keys to store.  If not specified -- entire dictionaries are stored
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

    def get_values(self, keys):
        return [[d[k] for k in keys] for d in self.data]

    def __call__(self, data):
        if self.keys:
                    self.data.append({key: data[key] for key in self.keys if key in data})

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

    def __init__(self, assignments):
        """
        Use OrderedDict when order of remapping matters
        """
        assert (isinstance(assignments, dict))
        self.assignments = assignments

    def __call__(self, data):
        # TODO: unittest
        data = data.copy()
        for from_, to_ in self.assignments.items():
            if from_ in data:
                data[to_] = data.pop(from_)
        yield data


# TODO: test
@auto_repr
class sub(object):
    """Apply re.sub regular expression substitutions to specified items"""

    def __init__(self, subs, ok_missing=False):
        """

        Parameters
        ----------
        subs: dict of key -> dict of pattern -> replacement
        """
        self.subs = subs
        self.ok_missing = ok_missing

    def __call__(self, data):
        data = data.copy()
        for key, subs in self.subs.items():
            for from_, to_ in subs.items():
                if key not in data and self.ok_missing:
                    continue
                data[key] = re.sub(from_, to_, data[key])
        yield data


@auto_repr
class assign(object):
    """Class node to provide assignment of items in data

    With "interpolate" it allows for insertion of values

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
        assert (isinstance(assignments, dict))
        self.assignments = assignments
        self.interpolate = interpolate

    def __call__(self, data):
        data_ = data.copy()  # we need to operate on a copy
        for k, v in self.assignments.items():
            data_[k] = v % data if self.interpolate else v
        yield data_


# class prune(object):

def get_url_filename(data):
    yield updated(data, {'filename': get_url_straight_filename(data['url'])})


def get_disposition_filename(data):
    """For the URL request content filename disposition
    """
    yield updated(data, {'filename': get_url_disposition_filename(data['url'])})


class _act_if(object):
    """Base class for nodes which would act if input data matches specified values

    Should generally be not used directly.  If used directly,
    no action is taken, besides possibly regexp matched groups
    populating the `data`
    """

    def __init__(self, values, re=False, negate=False):
        """

        Parameters
        ----------
        values: dict
          Key/value pairs to compare arrived data against.  Would raise
          FinishPipeline if all keys have matched target values
        re: bool, optional
          If specified, values are to be treated as regular expression to be
          searched. If re and expression includes groups, those will also
          populate yielded data
        negate: bool, optional
          Reverses, so acts (skips, etc) if no match
        """
        self.values = values
        self.re = re
        self.negate = negate

    def __call__(self, data):
        #import ipdb; ipdb.set_trace()
        comp = re.search if self.re else lambda x, y: x == y
        matched = True
        # finds if all match
        data_ = data.copy()
        for k, v in iteritems(self.values):
            res = k in data and comp(v, data[k])
            if not res:
                # do nothing and pass the data further
                matched = False
                break
            if self.re:
                assert(res)
                data_.update(res.groupdict())

        for v in (self._act_mismatch
                  if matched != self.negate
                  else self._act_match)(data_):
            yield v

    # By default, nothing really is done -- so just produce the same
    # data.  Sub-classes will provide specific custom actions in one
    # or another case
    def _act_mismatch(self, data):
        return [data]

    def _act_match(self, data):
        return [data]


@auto_repr
class interrupt_if(_act_if):
    """Interrupt further pipeline processing whenever obtained data matches provided value(s)"""

    def _act_mismatch(self, data):
        raise FinishPipeline


@auto_repr
class skip_if(_act_if):
    """Skip (do not yield anything) further pipeline processing whenever obtained data matches provided value(s)"""

    def _act_mismatch(self, data):
        return []  # nothing will be yielded etc


@auto_repr
class continue_if(_act_if):
    """Continue if matched

    An inverse of skip_if"""

    def _act_match(self, data):
        return []


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

    If provided function returns a generator, each item is returned separately

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
                # we need to place it into the copy of data
                data_ = data.copy()
                if len(outputs_) > 1:
                    # we were requested to have multiple outputs,
                    # then the function should have provided matching multiple values
                    assert (len(return_value) == len(outputs_))
                else:
                    return_value = [return_value]  # for uniformity

                for k, v in zip(outputs_, return_value):
                    data_[k] = v
                yield data_
            else:
                # TODO: does it make sense to yield the same multiple times ever
                # if we don't modify it???
                yield data

    in_args = list(_string_as_list(data_args)) + list(_string_as_list(data_kwargs))
    str_args = (
        func.__name__ if hasattr(func, '__name__') else '',
        id(func),
        ', '.join(in_args) if in_args else "no",
        ', '.join(_string_as_list(outputs)) if outputs else "no"
    )
    func_node.__doc__ = """Function %s#0x%x wrapped into a node.

It expects %r keys to be provided in the data and output will be assigned to %s
keys in the output %s
""" % (
        str_args + (
        (' Additional keyword arguments: %s' % kwargs) if kwargs else "",
        )
    )

    # unfortunately overloading __str__ doesn't work
    _str = "<node:%s#0x%x in_args: %r outputs: %r" % str_args
    if kwargs:
        _str += " kwargs: %s" % ', '.join("%s=%r" % i for i in kwargs.items())
    _str += '>'
    func_node._custom_str = _str
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
          Fail if no file matched throughout the life-time of this object, i.e.
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


    Example
    -------

    TODO
    """

    def __init__(self, key, mapping, default=None, missing='raise', re=False):
        """
        Parameters
        ----------
        key: str
        mapping: dict
        re: bool, optional
          Either mapping keys define the regular expressions.  Note that in case
          multiple regular expressions match, all of them would "work it"
        default: node or pipeline, optional
          Node or pipeline to use if no mapping was found
        missing: ('raise', 'stop', 'skip'), optional
          If value is missing in the mapping or key is missing in data
          (yeah, not differentiating atm), and no default is provided:
          'raise' - would just raise KeyError, 'stop' - would not yield
          anything in effect stopping any down processing, 'skip' - would
          just yield input data
        """
        self.key = key
        self.mapping = mapping
        self.re = re
        # trying self.missing assigning just for the sake of auto_repr
        self.missing = self._missing = missing
        self.default = default

    @property
    def missing(self):
        return self._missing

    @missing.setter
    def missing(self, value):
        assert (value in {'raise', 'skip', 'stop'})
        self._missing = value

    def __call__(self, data):
        # make decision which sub-pipeline

        key_value = data[self.key]
        if not self.re:
            try:
                pipelines = [self.mapping[key_value]]
            except KeyError:
                pipelines = []
        else:
            # find all the matches
            pipelines = [
                pipeline
                for regex, pipeline in self.mapping.items()
                if re.match(regex, key_value)
            ]

        if not pipelines:  # None has matched
            if self.default is not None:
                pipelines = [self.default]
            elif self.missing == 'raise':
                raise KeyError(
                    "Found no matches for %s == %r %s %r" % (
                    self.key,
                    key_value,
                    "matching one of" if self.re else "among specified",
                    list(self.mapping.keys()))
                )
            elif self.missing == 'skip':
                yield data
                return
            elif self.missing == 'stop':
                return

        for pipeline in pipelines:
            if pipeline is None:
                yield data
                return

            if not isinstance(pipeline, PIPELINE_TYPES):
                # it was a node, return its output
                gen = pipeline(data)
            else:
                gen = xrun_pipeline(pipeline, data)

            # run and yield each result
            for out in gen:
                yield out


@auto_repr
class debug(object):
    """Helper node to fall into debugger (pdb for now) whenever node is called"""

    def __init__(self, node, when='before'):
        """
        Parameters
        ----------
        node: callable
        when: str, optional
          Determines when to enter the debugger:
          - before: right before running the node
          - after: after it was ran
          - empty: when node produced no output
        """
        self.node = node
        self.when = when

    def __call__(self, data):
        node = self.node
        when = self.when
        if when == 'before':
            lgr.info("About to run %s node", node)
            pdb.set_trace()

        n = 0
        for out in node(data):
            n += 1
            yield out

        if when == 'after' or (when == 'empty' and n == 0):
            lgr.info("Ran node %s which yielded %d times", node, n)
            pdb.set_trace()

