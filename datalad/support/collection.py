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
                                                          self.keys())

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

    def __setitem__(self, key, value):
        super(Collection, self).__setitem__(key, value)
        self_uri = self.meta.value(predicate=RDF.type, object=DLNS.Collection)
        if self_uri is None:
            raise CollectionBrokenError()  # TODO: Proper exceptions
        key_uri = self[key].meta.value(predicate=RDF.type, object=DLNS.Handle)
        if key_uri is None or key_uri == DLNS.this:
            if self[key].url is not None:
                # replace URI in graph:
                # Note: This assumes handle.meta is modifiable, meaning repo
                #       backends currently need to override it.
                from rdflib import URIRef
                self[key].meta.remove((key_uri, RDF.type, DLNS.Handle))
                key_uri = URIRef(self[key].url)
                self[key].meta.add((key_uri, RDF.type, DLNS.Handle))
            else:
                super(Collection, self).__delitem__(key)
                raise ValueError("Handle '%s' has neither a valid URI (%s) nor an URL." % (key, key_uri))
        self.meta.add((self_uri, DCTERMS.hasPart, key_uri))
        self.store.add_graph(self[key].meta)

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
        super(MetaCollection, self).__init__()

        self.name = name
        self.store = IOMemory()

        if isinstance(src, MetaCollection):
            self.update(src)
            self.name = src.name
            # TODO: See Collection: How to treat names in case of a copy?

        elif isinstance(src, list):
            for item in src:
                if isinstance(item, Collection):
                    self[str(item.name)] = item
                else:
                    e_msg = "Can't retrieve collection from %s." % type(item)
                    lgr.error(e_msg)
                    raise TypeError(e_msg)

        elif isinstance(src, dict):
            for key in src:
                if isinstance(src[key], Collection):
                    self[key] = src[key]
                else:
                    e_msg = "Can't retrieve collection from %s." % \
                            type(src[key])
                    lgr.error(e_msg)
                    raise TypeError(e_msg)

        elif src is None:
            pass
        else:
            e_msg = "Invalid source type for MetaCollection: %s" % type(src)
            lgr.error(e_msg)
            raise TypeError(e_msg)

        # join the stores:
        for collection in self:
            for graph in self[collection].store.contexts():
                self.store.add_graph(graph)
                # TODO: Note: Removed all the copying of the graphs and correcting
                # their references, since we now always use
                # 'collection/branch/handle' as key. But: Implementation of
                # this changed behaviour is not well tested yet.

        self.conjunctive_graph = ConjunctiveGraph(store=self.store)

    def __setitem__(self, key, value):
        if not isinstance(value, Collection):
            raise TypeError("Can't add non-Collection type to MetaCollection.")

        super(MetaCollection, self).__setitem__(key, value)
        for graph in value.store.contexts():
            self.store.add_graph(graph)

    def __delitem__(self, key):
        # delete the graphs of the collection and its handles:
        for graph in self[key].store.contexts():
            self.store.remove_graph(graph)
        # delete the entry itself:
        super(MetaCollection, self).__delitem__(key)

    def query(self):
        """ Perform query on the meta collection.
        Note: It's self.conjunctive_graph or self.store respectively,
        what is to be queried here.
        """
        pass
