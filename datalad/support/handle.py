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

from .metadatahandler import DLNS, RDF, Graph, Literal
from.exceptions import ReadOnlyBackendError


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

    Abstract base class defining an interface, that needs to be implemented
    by any class that aims to provide a backend for handles.
    An instance of a derived class serves as a runtime representation of the
    handle's metadata. That metadata is represented by a named graph.
    'update_metadata' and 'commit_metadata' are used to synchronize that graph
    with the physical backend.

    """

    __metaclass__ = ABCMeta

    def __init__(self):
        self._graph = None

    def __repr__(self):
        return "<Handle name=%s (%s)>" % (self.name, type(self))

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
    def update_metadata(self):
        """Update the graph containing the handle's metadata.

        Called to update 'self._graph' from the handle's backend.
        Creates a named graph, whose identifier is the name of the handle.
        """
        pass

    @abstractmethod
    def commit_metadata(self, msg="Metadata updated."):
        """Commit the metadata graph of a handle to its storage backend.

        A backend can deny to write handle data. In that case is should raise
        a ReadOnlyBackendError.

        Parameters
        ----------
        msg: optional commit message.

        Raises
        ------
        ReadOnlyBackendError
        """
        pass

    def get_metadata(self):
        if self._graph is None:
            lgr.debug("Updating graph of handle '%s' from backend." %
                      self.name)
            self.update_metadata()
        return self._graph

    # TODO: Not sure yet, whether setting the graph directly should
    # be allowed. This involves change of the identifier, which may
    # mess up things. Therefore may be don't let the user set it.
    # Triples can be modified anyway.
    # This also leads to the thought of renaming routine, which would need
    # to copy the entire graph to a new one with a new identifier.
    def set_metadata(self, graph):
        self._graph = graph

    meta = property(get_metadata, set_metadata)

    @property
    def name(self):
        return str(self.meta.identifier)


class RuntimeHandle(Handle):
    """Pure runtime Handle without a persistent backend.

    This kind of a handle can only be used as a "virtual" handle, that has no
    physical storage.

    Note: For now, there is no usecase.
    It serves as an example and a test case.
    """

    def __init__(self, name):
        super(RuntimeHandle, self).__init__()
        self._graph = Graph(identifier=Literal(name))
        self._graph.add((DLNS.this, RDF.type, DLNS.Handle))

    @property
    def url(self):
        return None

    def update_metadata(self):
        pass

    def commit_metadata(self, msg="Metadata updated."):
        raise ReadOnlyBackendError("Can't commit RuntimeHandle.")

