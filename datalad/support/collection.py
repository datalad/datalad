# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Implements datalad collection metadata representation.
"""


import logging
from abc import ABCMeta, abstractmethod, abstractproperty

from rdflib import ConjunctiveGraph
from rdflib.plugins.memory import IOMemory
from six import iterkeys

from datalad.support.exceptions import CollectionBrokenError
from datalad.support.metadatahandler import DLNS, RDF, DCTERMS

lgr = logging.getLogger('datalad.collection')


class Collection(dict):

    __metaclass__ = ABCMeta

    def __init__(self):
        super(Collection, self).__init__()

        self.store = IOMemory()
        self._graph = None

    def __repr__(self):
        return "<Collection name=%s (%s), handles=%s>" % (self.name,
                                                          type(self),
                                                          list(iterkeys(self)))

    # TODO: Not sure yet, whether this should be abstract or provide a
    #       default implementation
    @abstractmethod
    def __eq__(self, other):
        pass

    # TODO: Does the URI linking make sense, regarding lazy loading of the
    # handles themselves? This leads to all the handle.meta being called and
    # therefore constructed!
    # But: If we don't override setitem and delitem - when to update collection
    # graph?
    # - on update_store only? But then collection-level would not be actually
    #   valid rdf until update_store()

    def __delitem__(self, key):
        self_uri = self.meta.value(predicate=RDF.type, object=DLNS.Collection)
        if self_uri is None:
            raise CollectionBrokenError()
        key_uri = self[key].meta.value(predicate=RDF.type, object=DLNS.Handle)
        if key_uri is None or key_uri == DLNS.this:
            raise ValueError("Handle '%s' has invalid URI: %s." % (key, key_uri))
        self.meta.remove((self_uri, DCTERMS.hasPart, key_uri))
        self.store.remove_graph(self[key].name)
        super(Collection, self).__delitem__(key)

    def __setitem__(self, handle_name, handle):
        """Sugaring to be used to assign a brand new handle, not known to the
        collection.
        """
        self.register_handle(handle, handle_name=handle_name, add_handle_uri=True)

    def register_handle(self, handle, handle_name=None, add_handle_uri=None):
        """Register a given handle

        Parameters
        ----------
        handle_name: str
        handle: Handle
        add_handle_uri: bool or None, optional
          Add handle uri to the collection meta-data.  If None, and no name was
          provided (thus it could have not being known) -- assume True
        """

        # if no handle_name was provided -- take it from the handle
        if handle_name is None:
            handle_name = handle.name
            if add_handle_uri is None:
                add_handle_uri = True

        super(Collection, self).__setitem__(handle_name, handle)

        if add_handle_uri is None:
            add_handle_uri = False

        if add_handle_uri:
            self_uri = self.meta.value(predicate=RDF.type, object=DLNS.Collection)
            if self_uri is None:
                raise CollectionBrokenError()  # TODO: Proper exceptions

            # Load it from the handle itself
            key_uri = self[handle_name].meta.value(predicate=RDF.type, object=DLNS.Handle)
            if key_uri is None or key_uri == DLNS.this:
                if self[handle_name].url is not None:
                    # replace URI in graph:
                    # Note: This assumes handle.meta is modifiable, meaning repo
                    #       backends currently need to override it.
                    from rdflib import URIRef
                    self[handle_name].meta.remove((key_uri, RDF.type, DLNS.Handle))
                    key_uri = URIRef(self[handle_name].url)
                    self[handle_name].meta.add((key_uri, RDF.type, DLNS.Handle))
                else:
                    super(Collection, self).__delitem__(handle_name)
                    raise ValueError("Handle '%s' has neither a valid URI (%s) nor an URL." % (handle_name, key_uri))
            self.meta.add((self_uri, DCTERMS.hasPart, key_uri))
            self.store.add_graph(self[handle_name].meta)

    def fsck(self):
        """Verify that the collection is in legit state. If not - FIX IT!
        """
        # TODO: verify that all the registered handles URIs are valid:
        #  1. that local path key_uris point to existing handles paths
        #  2. Go through local handles and run their .fsck
        # Subclasses should extend the checks (e.g. checking git fsck, git annex fsck, etc)
        raise NotImplementedError()

    @property
    def name(self):
        """Name of the collection.

        Returns
        -------
        str
        """
        return str(self.meta.identifier)

    @abstractproperty
    def url(self):
        """URL of the physical representation of the collection.

        This is a read-only property, since an url can only be provided by a
        physically existing collection. It doesn't make sense to tell a backend
        to change it.

        Returns
        -------
        str
        """
        pass

    def get_meta(self):
        if self._graph is None:
            lgr.debug("Updating collection metadata graph.")
            self.update_metadata()
        return self._graph

    def set_meta(self, data):
        self._graph = data

    meta = property(get_meta, set_meta, doc="""
    Named rdflib.Graph representing the metadata of the collection.
    This is a lazy loading property, that is created only when accessed. Note,
    that this is not necessarily always in sync with the underlying backend.
    Therefore `update_metadata` and `commit` are provided, to explicitly make
    sure it's synchronized.""")

    @abstractmethod
    def update_metadata(self):
        """Update the graph containing the collection's metadata.

        Called to update 'self._graph' from the collection's backend.
        Creates a named graph, whose identifier is the name of the collection.
        """
        pass
        # TODO: what about runtime changes? discard? Meh ...

    @abstractmethod
    def commit(self, msg="Collection updated."):
        # commit metadata only? Or even changed handle list? The latter!
        pass

    def update_graph_store(self):
        """Update the entire graph store.

        Update all the metadata graphs from their backends, the collection
        level metadata as well as the handles' metadata. Makes sure, that all
        the graphs are available and up-to-date in the collection's graph
        store. This is especially needed before querying the graph store, due
        to the fact, that graphs are loaded on demand.
        """

        self.update_metadata()

        # TODO: Currently we update from backend here. Maybe just make sure
        # every graph is added and make update from backend an option?
        # Additionally, what about changes in backend?
        # => handle may not be in self yet!
        for handle in self:
            self[handle].update_metadata()
            self.store.add_graph(self[handle].meta)

    # overriding dict.update():
    # def update(self, other=None, **kwargs):
    #     super(Collection, self).update(other, **kwargs)
    #     TODO: Update collection-level metadata (hasPArt)
    #           => implicit: setitem, delitem?

    def sparql_query(self, query):
        # don't query store directly! This wouldn't ensure the store to be
        # fully loaded.
        self.update_graph_store()
        return ConjunctiveGraph(store=self.store).query(query)

    # TODO:
    # override pop()!
    # what about clear()?
    # copy()?


class MetaCollection(dict):
    """A collection of collections.

    This is a dictionary, which's keys are the collections' names.
    Values are Collection instances.

    Like Collections this class collects the named metadata graphs of its items
    in a graph store (and its conjunctive graph), that can be queried.
    Additionally, a MetaCollection can have a name.

    Attributes of a MetaCollection:
    name:               str
    store:              IOMemory
    conjunctive_graph:  ConjunctiveGraph
    """

    def __init__(self, src=None, name=None):
        """

        Parameters
        ----------
        src
        name

        Returns
        -------

        """
        super(MetaCollection, self).__init__()

        self.name = name

        # TODO: Not sure whether 'store' and 'conjunctive_graph' should be
        #       public. (requires the user to know exactly when to update)
        self.store = IOMemory()

        if src is not None:
            # retrieve key, value pairs for the dictionary:
            if isinstance(src, dict):
                self.update(src)
            else:
                # assume iterable of Collection items:
                for item in src:
                    self[item.name] = item

            # collect the graphs in the store:
            # Note: Only acquires graphs, that are currently loaded by the
            #       collections!

            # TODO: Move to isinstance(dict)-block. Due to assignement this is
            # done already in case of a non-dict!
            for collection in self:
                for graph in self[collection].store.contexts():
                    self.store.add_graph(graph)
                    # TODO:
                    # Note: Removed all the copying of the graphs and
                    #       correcting their references, since we now always
                    #       use 'collection/handle' as key.
                    # But:  Implementation of this changed behaviour is not
                    #       well tested yet.

        self.conjunctive_graph = ConjunctiveGraph(store=self.store)

    def __setitem__(self, collection_name, collection):
        super(MetaCollection, self).__setitem__(collection_name, collection)
        # add the graphs of the collection and its handles to the graph store:
        for graph in collection.store.contexts():
            self.store.add_graph(graph)

    # TODO: if handle names always use collection_name/handle_name in the
    # context of collections, __delitem__ and pop should use this pattern to
    # remove graphs instead of looking at the CURRENT store of the collection!

    def __delitem__(self, collection_name):
        # remove the graphs of the collection and its handles from the graph
        # store:
        for graph in self[collection_name].store.contexts():
            self.store.remove_graph(graph)
        # delete the entry itself:
        super(MetaCollection, self).__delitem__(collection_name)

    def pop(self, collection_name, default=None):
        # remove the graphs of the collection and its handles from the graph
        # store:
        for graph in self[collection_name].store.contexts():
            self.store.remove_graph(graph)
        return super(MetaCollection, self).pop(collection_name,
                                               default=default)

    def update_graph_store(self):
        """
        """

        del self.store
        self.store = IOMemory()

        for collection in self:
            self[collection].update_graph_store()
            for graph in self[collection].store.contexts():
                self.store.add_graph(graph)

        self.conjunctive_graph = ConjunctiveGraph(store=self.store)

    def query(self, query, update=True):
        """Perform query on the meta collection.

        Parameters
        ----------
        query
        update

        Returns
        -------

        """

        if update:
            self.update_graph_store()
        return self.conjunctive_graph.query(query)


    # TODO: to be a *Collection it must fulfill the same API?