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
    """Interface to be implemented by backends for handles.

    Abstract class defining an interface, that needs to be implemented
    by any class that aims to provide a backend for handles.
    """

    __metaclass__ = ABCMeta

    @abstractproperty
    def id(self):
        """id of handle.

        This is a read-only property, since an id can only be provided by a
        physically existing handle. It doesn't make sense to tell a backend to
        change it.

        Note: For now, this id is provided but not used anywhere. It's not
        clear yet whether to keep it at all.

        Returns:
        --------
        str
        """
        pass

    @abstractproperty
    def url(self):
        """url of the physical representation of a handle.

        This is a read-only property, since an url can only be provided by a
        physically existing handle. It doesn't make sense to tell a backend to
        change it.

        Returns:
        --------
        str
        """
        pass

    @abstractmethod
    def get_name(self):
        """Get the (default) name of handle.

        A handle's name is defined by and unique within a collection.
        Nevertheless it has a default name it knows about by itself.
        This method is supposed to return the "most valid" name the backend
        knows. So, a backend that is somehow connected to a collection should
        return the handle's name with respect to this collection instead of its
        default name.

        Returns:
        --------
        str
        """
        pass

    @abstractmethod
    def set_name(self, name):
        """Set a handle's name.

        Whether it's the handle's default name to be set or a collection's name
        for the handle depends on the backend.

        A backend can deny to write handle data. In that case is should raise
        an exception.

        TODO: Define a ReadOnlyException or sth.

        Parameters:
        -----------
        name: str
        """
        pass

    name = abstractproperty(get_name, set_name)

    @abstractmethod
    def get_metadata(self):
        """Get a graph containing the handle's metadata.

        Returns:
        --------
        rdflib.Graph
        """
        pass

    @abstractmethod
    def set_metadata(self, meta):
        """Set the metadata of a handle.

        A backend can deny to write handle data. In that case is should raise
        an exception.

        TODO: Define a ReadOnlyException or sth.

        Parameters:
        -----------
        meta: rdflib.Graph
        """
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