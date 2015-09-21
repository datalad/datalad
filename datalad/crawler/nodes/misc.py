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

class Sink(object):
    """A rudimentary node to sink/collect all the data passed into it
    """

    # TODO: add argument for selection of fields of data to keep
    def __init__(self):
        self.data = []

    def get_fields(self, *keys):
        return [(d[k] for k in keys) for d in self.data]

    def __call__(self, **data):
        # ??? for some reason didn't work when I made entire thing a list
        self.data.append(data)
        yield data


class rename(object):
    """Rename fields in data for subsequent nodes
    """
    def __init__(self, mapping):
        """

        Use OrderedDict when order of remapping matters
        """
        self._mapping = mapping

    def __call__(self, **data):
        # TODO: unittest
        data = data.copy()
        for from_, to_ in self._mapping:
            if from_ in data:
                data[to_] = data.pop(from_)
        yield data

#class prune(object):
