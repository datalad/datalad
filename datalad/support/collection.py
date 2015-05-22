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

from abc import ABCMeta, abstractmethod
from copy import deepcopy
import logging
import gc

from rdflib import Graph, URIRef, ConjunctiveGraph
from rdflib.plugins.memory import IOMemory

from .handle import Handle
from .metadatahandler import DLNS

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

        Returns:
        --------
        dictionary of Handle
          keys are the handles' names, values the corresponding Handle
          instances
        """
        pass

    @abstractmethod
    def get_collection(self):
        """Get the metadata of the collection itself.

        Returns:
        --------
        dictionary
          By now there are just two keys:
            'name': str
            'meta': rdflib.Graph
        """

    @abstractmethod
    def commit_collection(self, collection, msg):
        """Commit a collection.

        Commits changes of the runtime representation `collection` to the
        backend. Accepts a commit message.

        Parameters:
        -----------
        collection: Collection
        msg: str
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
            self.name = src.name
            self.store = IOMemory()
            for graph in src.store.contexts():
                self.store.add_graph(graph)
                if graph.identifier == self.name:
                    self.meta = graph
                else:
                    self[graph.identifier].meta = graph

            self.conjunctive_graph = ConjunctiveGraph(store=self.store)

        elif isinstance(src, CollectionBackend):
            self._backend = src
            self._reload()
        elif src is None:
            self._backend = None
            self.name = name
            self.store = IOMemory()
            self.meta = Graph(store=self.store, identifier=URIRef(self.name))
            self.conjunctive_graph = ConjunctiveGraph(store=self.store)

        else:
            lgr.error("Unknown source for Collection(): %s" % type(src))
            raise TypeError('Unknown source for Collection(): %s' % type(src))

    def __delitem__(self, key):
        super(Collection, self).__delitem__(key)
        self.meta.remove((URIRef(self.name), DLNS.contains, URIRef(key)))
        self.store.remove_graph(URIRef(key))

    def __setitem__(self, key, value):
        super(Collection, self).__setitem__(key, value)
        self.meta.add((URIRef(self.name), DLNS.contains, URIRef(key)))
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
        self.name = collection_data['name']

        # TODO: May be a backend can just pass a newly created store containing
        # all the needed graphs. Would save us time and space for copy, but
        # seems to be less flexible in case we find another way to store a set
        # of named graphs and their conjunctive graph without the need of every
        # collection to have its own store.
        # Note: By using store.add() there seems to be no copy at all.
        # Need to check in detail, how this is stored and whether it still
        # works as intended.
        # Note 2: Definitely not a copy and seems to work. Need more querie to
        # check.

        # cleanup old store, if exists
        if self.store:
            self.store.gc()
            del self.store
            gc.collect()
        # create new store for the graphs:
        self.store = IOMemory()

        # add collection's own graph:
        self.store.add_graph(collection_data['meta'])
        self.meta = collection_data['meta']

        # add handles' graphs:
        for handle in self:
            self.store.add_graph(self[handle].meta)
            # add reference in collection graph:
            # TODO: Is this still needed or is it correct if it's done by
            # the backend?
            # Either way:
            # TODO: check whether this referencing works as intended:
            self.meta.add((URIRef(self.name), DLNS.contains, URIRef(handle)))

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


# #######################
# TODO: MetaCollection is a Collection of Collections. So, how to reflect this
# in implementation? Is it a dictionary too? Or is it a Collection?
# Or is a Collection a special MetaCollection?
# #######################

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
            self.name = src.name  #? See Collection: How to treat names in case of a copy?
            self.store = deepcopy(src.store)

        elif isinstance(src, list):
            for item in src:
                if isinstance(item, Collection):
                    self[item.name] = item
                elif isinstance(item, CollectionBackend):
                    self[item.get_name] = Collection(src=item)
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
                # need to avoid conflicts with handles' names,
                # therefore name them 'collection/handle'
                # TODO: This needs further investigation on how it can be dealt
                # with in a reasonable way. May be handle names always need to
                # be created that way for consistency.
                identifier = graph.identifier \
                    if graph.identifier == collection \
                    else collection + '/' + graph.identifier

                # create a copy of the graph in self.store:
                new_graph = Graph(store=self.store, identifier=identifier)
                for triple in graph:
                    new_graph.add(triple)

                if identifier == collection:
                    # correct references of collection graph:
                    for old_handle_identifier in new_graph.objects(
                            URIRef(collection), DLNS.contains):
                        new_graph.add((URIRef(collection), DLNS.contains,
                                       URIRef(collection + '/' +
                                              old_handle_identifier)))
                        new_graph.remove((URIRef(collection), DLNS.contains,
                                          old_handle_identifier))

        self.conjunctive_graph = ConjunctiveGraph(store=self.store)

    def __setitem__(self, key, value):
        # TODO: See collections
        pass

    def __delitem__(self, key):
        # TODO: See collections
        pass

    def update(self, remote=None, branch=None):
        # reload (all) branches
        # TODO: In that sense, it's obsolete.

        pass

    def query(self):
        """ Perform query on the meta collection.
        Note: It's self.conjunctive_graph or self.store respectively,
        what is to be queried here.
        """