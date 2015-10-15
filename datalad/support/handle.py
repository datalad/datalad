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

from rdflib import URIRef, Graph, Literal

from ..support.metadatahandler import DLNS, RDF

from .annexrepo import AnnexRepo


lgr = logging.getLogger('datalad.handle')


class HandleBackend(object):
    """Interface to be implemented by backends for handles.

    Abstract class defining an interface, that needs to be implemented
    by any class that aims to provide a backend for handles.
    """

    __metaclass__ = ABCMeta

    @abstractproperty
    def url(self):
        """url of the physical representation of a handle.

        This is a read-only property, since an url can only be provided by a
        physically existing handle. It doesn't make sense to tell a backend to
        change it.

        Returns
        -------
        str
        """
        pass

    @abstractmethod
    def get_metadata(self, files=None):
        """Get a graph containing the handle's metadata.

        Returns
        -------
        rdflib.Graph
        """
        # TODO: doc `files` and may be find a more general name
        pass

    @abstractmethod
    def set_metadata(self, meta, msg=None):
        """Set the metadata of a handle.

        A backend can deny to write handle data. In that case is should raise
        an exception.

        TODO: Define a ReadOnlyException or sth.

        Parameters
        ----------
        meta: rdflib.Graph
        msg: optionally a "commit-message"
        """
        pass


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
            self.url = self._backend.url
            self.meta = self._backend.get_metadata()

        elif isinstance(src, Handle):
            # TODO: Correct behaviour of copy constructor?
            self._backend = src._backend
            self.meta = src.meta
            self.url = src.url

        elif src is None:
            self._backend = None
            self.meta = Graph(identifier=Literal(name))
            self.meta.add((DLNS.this, RDF.type, DLNS.Handle))
            self.url = None

        else:
            e_msg = "Invalid source for Handle: %s." % type(src)
            lgr.error(e_msg)
            raise TypeError(e_msg)

    def commit(self, msg="Handle updated."):

        if not self._backend:
            lgr.error("Missing handle backend.")
            raise RuntimeError("Missing handle backend.")

        self._backend.set_metadata(self.meta, msg)

    @property
    def name(self):
        return self.meta.identifier

