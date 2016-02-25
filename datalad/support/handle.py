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

lgr = logging.getLogger('datalad.handle')


class Handle(object):
    """Representation of a Handle's metadata.

    This is a top-level representation of a handle. In that sense a handle is
    a set of metadata, represented as a named rdflib.Graph. Parts of the
    metadata may be accessible directly by an attribute without the need to
    explicitly query the graph. The latter by now counts especially for the
    attributes `url` and `name`. Additionally, this kind of a handle is linked
    to an underlying backend, that may also provide access to the actual
    content of the handle.
    Note, that this graph is a runtime object residing in memory. The
    `update_metadata` and `commit_metadata` methods are meant to be used to
    synchronize the graph and the underlying storage.

    This is an abstract class, that basically defines a general interface to
    handles. Any backend to be supported should be implemented by deriving from
    this class.
    """

    __metaclass__ = ABCMeta

    def __init__(self):
        self._graph = None
        self._update_listeners = list()

    def __repr__(self):
        return "<Handle name=%s (%s)>" % (self.name, type(self))

    def __eq__(self, other):
        # abstract?
        raise NotImplementedError("TODO")

    def register_update_listener(self, listener):
        """

        Parameters
        ----------
        listener: callable
        """

        for l in self._update_listeners:
            if l is listener:
                return
        self._update_listeners.append(listener)

    def remove_update_listener(self, listener):
        """

        Parameters
        ----------
        listener: callable
        """

        self._update_listeners.remove(listener)

    def notify_update_listeners(self):
        for listener in self._update_listeners:
            listener(self)

    @abstractproperty
    def url(self):
        """URL of the physical representation of the handle.

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

    # TODO: Maybe rename to just commit?
    @abstractmethod
    def commit_metadata(self, msg="Metadata updated."):
        """Commit the metadata graph of a handle to its storage backend.

        A backend can deny to write handle data. In that case is should raise
        a ReadOnlyBackendError.

        Parameters
        ----------
        msg: str
            optional commit message.

        Raises
        ------
        ReadOnlyBackendError
        """
        pass

    def get_metadata(self):
        if self._graph is None:
            lgr.debug("Updating handle graph from backend.")
            self.update_metadata()
        return self._graph

    # TODO: Not sure yet, whether setting the graph directly should
    # be allowed. This involves change of the identifier, which may
    # mess up things. Therefore may be don't let the user set it.
    # Triples can be modified anyway.
    # This also leads to the thought of renaming routine, which would need
    # to copy the entire graph to a new one with a new identifier.
    def set_metadata(self, data):
        self._graph = data

    # TODO: read-only in name?
    meta = property(get_metadata, set_metadata, doc="""
    Named rdflib.Graph representing the metadata of the handle.
    This is a lazy loading property, that is created only when accessed. Note,
    that this is not necessarily always in sync with the underlying backend.
    Therefore `update_metadata` and `commit_metadata` are provided,
    to explicitly make sure it's synchronized.""")

    @property
    def name(self):
        """Name of the handle.

        Returns
        -------
        str
        """
        return str(self.meta.identifier)
