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

from six import iteritems

from datalad.support.network import get_url_deposition_filename, get_url_straight_filename
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

    def get_fields(self, *keys):
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
    """Rename fields in data for subsequent nodes
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
    def __init__(self, assignments, interpolate=False):
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

def get_deposition_filename(data):
    """For the URL request content filename deposition
    """
    yield updated(data, {'filename': get_url_deposition_filename(data['url'])})

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
    """A node yielding incrementing integers in a data field (output by default)

    Primarily for testing
    """
    def __init__(self, n, output='output'):
        self.n = n
        self.output = output

    def __call__(self, data={}):
        for i in range(self.n):
            yield updated(data, {self.output: i})

