# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Implements datalad handle metadata representation.
"""

import logging
from abc import ABCMeta, abstractmethod, abstractproperty

from rdflib import URIRef, Graph


lgr = logging.getLogger('datalad.handle')


class HandleBackend(object):

    __metaclass__ = ABCMeta

    @abstractproperty
    def id(self):
        pass

    @abstractproperty
    def url(self):
        pass

    @abstractmethod
    def get_name(self):
        pass

    @abstractmethod
    def set_name(self, name):
        pass

    name = abstractproperty(get_name, set_name)

    @abstractmethod
    def get_metadata(self):
        pass

    @abstractmethod
    def set_metadata(self, meta):
        pass

    metadata = abstractproperty(get_metadata, set_metadata)


class Handle(object):
    """Representation of a Handle's metadata.

    Independent on its physical representation.
    """

    # TODO: May be all the data like url, id should directly go into the
    # metadata graph. If we need them without a desire to query/build the
    # metadata graph we would likely use HandleRepo instead of Handle anyway.

    def __init__(self, src=None, name=None):
        # TODO: Handling of 'name' option. See Collections.

        if isinstance(src, HandleBackend):
            self._backend = src
            self.id = self._backend.id
            self.url = self._backend.url
            self.name = self._backend.name
            self.metadata = self._backend.metadata

        elif isinstance(src, Handle):
            # TODO: Correct behaviour of copy constructor?
            # Does this mean, Handle is also a HandleBackend?
            # Additionally think about pure runtime handles, without any
            # backend. They would need to store the data, instead of linking
            # to a backend. But do we need such?
            self._backend = src
            self.id = self._backend.id
            self.url = self._backend.url
            self.name = self._backend.name
            self.metadata = self._backend.metadata

        elif src is None:
            self._backend = None
            self.id = None
            self.url = None
            self.name = name
            self.metadata = Graph(identifier=URIRef(self.name))

        else:
            e_msg = "Invalid source for Handle: %s." % type(src)
            lgr.error(e_msg)
            raise TypeError(e_msg)