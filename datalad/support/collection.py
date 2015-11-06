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

from abc import ABCMeta, abstractmethod, abstractproperty
from copy import deepcopy
import logging
import gc

from rdflib import Graph, URIRef, ConjunctiveGraph, Literal
from rdflib.plugins.memory import IOMemory

from .handle import Handle
from .metadatahandler import DLNS, RDF, DCTERMS

lgr = logging.getLogger('datalad.collection')


class CollectionBackend(object):
    """Interface to be implemented by backends for collections.

    Abstract class defining an interface, that needs to be implemented
    by any class that aims to provide a backend for collections.
    """

    __metaclass__ = ABCMeta

    @abstractmethod
    def get_handles(self):
        """Get a dictionary of Handle instances.

        The dictionary contains the handles that belong to the collection.

        Returns
        -------
        dictionary of Handle
          keys are the handles' names, values the corresponding Handle
          instances
        """
        pass

    @abstractmethod
    def get_collection(self):
        """Get the metadata of the collection itself.

        Returns named Graph.

        Returns
        -------
        rdflib.Graph
        """

    @abstractmethod
    def commit_collection(self, collection, msg):
        """Commit a collection.

        Commits changes of the runtime representation `collection` to the
        backend. Accepts a commit message.

        Parameters
        ----------
        collection: Collection
        msg: str
        """

    @abstractproperty
    def url(self):
        """

        :return:
        """


    # TODO: We'll probably need a method to get a url of the collection.
    # Since collections are branches of repos in case of a repo-backend,
    # just the url won't be sufficient. On the other hand, by now it remains
    # unclear whether or not "installing" a collection (cloning the repo) will
    # be needed. Nevertheless: Think how to obtain a clone/checkout of a certain
    # collection. Even if someone wants to do it without datalad he needs a way
    # to retrieve all needed information. Depending on desired API to this, it
    # could simply be done via the CollectionRepo instance instead of a
    # Collection instance.

# TODO: Add/remove for Collections and MetaCollections.
# Collection => done. It's a dictionary.
# So, let a meta collection be a dictionary of collections?
# Actually, that way the meta data isn't updated. So, add/remove handle
# probably still necessary.
#
# => just override __setitem__ and __delitem__!
#
# Done for collections.


# #############################################
# TODO: May it's possible to have only one graph store and use
# ReadOnlyGraphAggregate instead of ConjunctiveGraph for
# Collections/MetaCollections. Could save time and space. But need to figure
# out how general queries work with that one.
#
# Nope. ReadOnlyGraphAggregate doesn't limit query()-method to its scope.
# Still queries the whole store. At least when querying for a
# certain graph(i.e. handle/collection)
# #############################################


class Collection(dict):
    """A collection of handles.

    Runtime representation of a collection's metadata. This is independent on
    its physical representation and therefore uses any CollectionBackend to set
    and/or retrieve the data.

    A Collection is a dictionary, which's keys are the handles' names.
    The values are Handle instances representing the metadata of these handles.
    Additionally, a Collection has attributes to store data about the
    collection itself:

    Attributes of a collection:
    name:               str
    store:              IOMemory
    meta:               (named) Graph
    conjunctive_graph:  ConjunctiveGraph

    To represent the metadata, Collections use a named graph per handle and an
    additional named graph for collection level metadata. These graphs can be
    queried via the collection's graph store and its corresponding conjunctive
    graph.
    """

    def __init__(self, src=None, name=None):
        # TODO: What about the 'name' option? How to treat it, in case src
        # provides a name already? For now use it only if src==None.
        # type(src) == Collection => copy has its own 'name'?
        # type(src) == Backend => rename in backend?

        super(Collection, self).__init__()

        if isinstance(src, Collection):
            self._backend = None
            # TODO: confirm this is correct behaviour and document it.
            # Means, it is a pure runtime copy with no persistence and no
            # update from backend.

            self.update(src)
            self.store = IOMemory()
            for graph in src.store.contexts():
                self.store.add_graph(graph)
                if graph.identifier == Literal(src.name):
                    self.meta = graph
                else:
                    self[str(graph.identifier)].meta = graph

            self.conjunctive_graph = ConjunctiveGraph(store=self.store)

        elif isinstance(src, CollectionBackend):
            self._backend = src
            self.store = None
            # TODO: check for existence in reload() fails otherwise;
            # If it turns out, that reload is never required outside of
            # constructor, that check isn't needed!

            self._reload()
        elif src is None:
            self._backend = None
            self.store = IOMemory()
            self.meta = Graph(store=self.store, identifier=Literal(name))
            self.meta.add((DLNS.this, RDF.type, DLNS.Collection))
            self.conjunctive_graph = ConjunctiveGraph(store=self.store)

        else:
            lgr.error("Unknown source for Collection(): %s" % type(src))
            raise TypeError('Unknown source for Collection(): %s' % type(src))

    @property
    def name(self):
        return str(self.meta.identifier)

    @property
    def url(self):
        return self._backend.url

    def __delitem__(self, key):

        lgr.error("__delitem__ called.")
        self_uri = self.meta.value(predicate=RDF.type, object=DLNS.Collection)
        key_uri = self[key].meta.value(predicate=RDF.type, object=DLNS.Handle)
        self.meta.remove((self_uri, DCTERMS.hasPart, key_uri))
        self.store.remove_graph(self[key].name)
        super(Collection, self).__delitem__(key)

    def __setitem__(self, key, value):
        if not isinstance(value, Handle):
            raise TypeError("Can't add non-Handle object to a collection.")

        super(Collection, self).__setitem__(key, value)
        self_uri = self.meta.value(predicate=RDF.type, object=DLNS.Collection)
        key_uri = self[key].meta.value(predicate=RDF.type, object=DLNS.Handle)
        self.meta.add((self_uri, DCTERMS.hasPart, key_uri))
        self.store.add_graph(self[key].meta)

    def _reload(self):
        # TODO: When do we need to reload outside of the constructor?
        # May be override self.update() to additionally reload in case
        # there is a backend.

        if not self._backend:
            # TODO: Error or warning? Depends on when we want to call this one.
            # By now this should be an error (or even an exception).
            lgr.error("Missing collection backend.")
            return

        # get the handles as instances of class Handle:
        self.update(self._backend.get_handles())

        # get collection level data:
        collection_data = self._backend.get_collection()

        # TODO: May be a backend can just pass a newly created store containing
        # all the needed graphs. Would save us time and space for copy, but
        # seems to be less flexible in case we find another way to store a set
        # of named graphs and their conjunctive graph without the need of every
        # collection to have its own store.
        # Note: By using store.add() there seems to be no copy at all.
        # Need to check in detail, how this is stored and whether it still
        # works as intended.
        # Note 2: Definitely not a copy and seems to work. Need more queries to
        # check.

        # cleanup old store, if exists
        if self.store is not None:
            self.store.gc()
            del self.store
            gc.collect()
        # create new store for the graphs:
        self.store = IOMemory()

        # add collection's own graph:
        self.store.add_graph(collection_data)
        self.meta = collection_data

        # add handles' graphs:
        for handle in self:
            self.store.add_graph(self[handle].meta)

        # reference to the conjunctive graph to be queried:
        self.conjunctive_graph = ConjunctiveGraph(store=self.store)

    def query(self):
        # Note: As long as we use general SPARQL-Queries, no method is needed,
        # since this is a method of rdflib.Graph/rdflib.Store.
        # But we will need some kind of prepared queries here.
        # Also depends on the implementation of the 'ontology translation layer'
        pass

    def commit(self, msg="Collection updated."):

        if not self._backend:
            lgr.error("Missing collection backend.")
            raise RuntimeError("Missing collection backend.")

        self._backend.commit_collection(self, msg)


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
                elif isinstance(item, CollectionBackend):
                    new_item = Collection(src=item)
                    self[str(new_item.name)] = new_item
                else:
                    e_msg = "Can't retrieve collection from %s." % type(item)
                    lgr.error(e_msg)
                    raise TypeError(e_msg)

        elif isinstance(src, dict):
            for key in src:
                if isinstance(src[key], Collection):
                    self[key] = src[key]
                elif isinstance(src[key], CollectionBackend):
                    self[key] = Collection(src=src[key])
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
