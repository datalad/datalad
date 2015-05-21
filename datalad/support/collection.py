# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Implements datalad collections.
"""

import re
import os
from os.path import join as opj, basename
from abc import ABCMeta, abstractmethod, abstractproperty
from copy import deepcopy
import logging
import gc

from rdflib import Graph, URIRef, Namespace, ConjunctiveGraph
from rdflib.plugins.memory import IOMemory
from rdflib.namespace import RDF
from rdflib.exceptions import ParserError

from .gitrepo import GitRepo
from .handlerepo import HandleRepo
from .exceptions import CollectionBrokenError
from .metadatahandler import DLNS

lgr = logging.getLogger('datalad.collection')

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

    This is a dictionary, which's keys are the handles' names.

    TODO: Describe structure of values, once we are sure about this.
    By now it's: self[handle_name]['id']:   str
                                  ['url']:  str
                                  ['meta']: (named) Graph

    Attributes of a collection:
    name:               str
    store:              IOMemory
    meta:               (named) Graph
    conjunctive_graph:  ConjunctiveGraph
    _backend:           CollectionBackend
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
            self.store = deepcopy(src.store)

            # get references of the store's named graphs
            for graph in self.store.contexts():
                if graph.identifier == self.name:
                    self.meta = graph
                elif graph.identifier in self:
                    self[graph.identifier]['meta'] = graph
                else:
                    lgr.warning("Invalid Graph identifier: %s" %
                                graph.identifier)

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
        new_graph = Graph(store=self.store, identifier=URIRef(key))
        for triple in value['meta']:
            new_graph.add(triple)
        self[key]['meta'] = new_graph

    def _reload(self):
        # TODO: When do we need to reload outside of the constructor?
        # May be override self.update() to additionally reload in case
        # there is a backend.

        if not self._backend:
            # TODO: Error or warning? Depends on when we want to call this one.
            # By now this should be an error (or even an exception).
            lgr.error("Missing collection backend.")
            return

        #########################################################
        # Note (to be implemented in backend):
        # Backend should provide data and metadata by separated methods.
        # - data is a dictionary, which is used to update the collection
        #   dictionary containing the 'datalad-collection-data',
        #   i.e. handles' names, ids, paths
        # - metadata is dictionary as well; keys are the names of the graphs,
        #   value are the graphs. These graphs have to be copied to the store
        #   of the collection and referenced by an additional entry in the
        #   collection dictionary (self[handle_name]['meta']).
        #   the collection's own graph is referenced by self.meta
        # - finally the conjunctive graph is referenced by
        #   self.conjunctive_graph
        #########################################################
        # TODO: May be a backend can just pass a newly created store containing
        # all the needed graphs. Would save us time and space for copy, but
        # is less flexible in case we find another way to store a set of named
        # graphs and their conjunctive graph without the need of every
        # collection to have its own store.

        self.update(self._backend.get_collection())

        # cleanup old store, if exists
        if self.store:
            self.store.gc()
            del self.store
            gc.collect()
        # create new store for the graphs:
        self.store = IOMemory()

        # get dictionary with metadata graphs:
        metadata = self._backend.get_metadata()
        # TODO: May be sanity check: collection's name and the handles' names
        # have to be present as keys in metadata

        # create collection's own graph:
        self.name = self._backend.get_name()
        self.meta = Graph(store=self.store, identifier=URIRef(self.name))

        # copy collection level metadata into this graph:
        for triple in metadata[self.name]:
            self.meta.add(triple)

        # now copy the handles' graphs and add a reference to the
        # collection's graph:

        for handle in self:
            self[handle]['meta'] = Graph(store=self.store,
                                         identifier=URIRef(handle))
            for triple in metadata[handle]:
                self[handle]['meta'].add(triple)

            # TODO: check whether this referencing works as intended:
            self.meta.add((URIRef(self.name), DLNS.contains, URIRef(handle)))

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

    TODO: This possibly leads to unnecessary copies of the graphs, in case
    those Collection instances aren't used otherwise anyway.
    Think about a better way to do it.
    (not just another way, a better one! ;-) )

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


class CollectionBackend(object):
    # How to pass the branch (especially on reload) without the collection
    # knowing anything about branches? => Let the backend store it. But then we
    # need different backend instances for the same repo.

    __metaclass__ = ABCMeta

    @abstractmethod
    def get_name(self):
        # TODO: May be a property with set/get
        # or integrate uri_ref+name in get_collection's return format.
        pass

    @abstractmethod
    def get_collection(self):
        """
        Returns:
        --------
        dictionary of dictionary
          first level keys are the handles' names. Second level keys are
          'id' and 'url'
        """
        pass

    @abstractmethod
    def get_metadata(self):
        """
        Returns:
        --------
        dictionary of Graph
          keys are the handles' names, values are the handles' metadata graphs.
        """
        pass

    @abstractmethod
    def commit_collection(self, collection, msg):
        """
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


class CollectionRepoBranchBackend(CollectionBackend):
    # TODO: Better name

    # TODO: This has to deal with remote branches too!

    def __init__(self, repo, branch=None):
        """
        Parameters:
        -----------
        repo: CollectionRepo or str
          in case of a string it's interpreted as being the path to the
          repository in question.
        branch: str
        """
        if isinstance(repo, CollectionRepo):
            self.repo = repo
        elif isinstance(repo, basestring):
            self.repo = CollectionRepo(repo)
        else:
            msg = "Invalid repo type: %s" % type(repo)
            lgr.error(msg)
            raise TypeError(msg)
        self.branch = branch or self.repo.git_get_active_branch()

    def get_collection(self):
        return self.repo.get_handles_data(self.branch)

    def get_metadata(self):
        return self.repo.get_metadata(self.branch)

    def get_name(self):
        # TODO: Not sure yet, whether this naming is the way to go.
        return self.repo.name + '/' + self.branch

    def commit_collection(self, collection, msg):
        self.repo.commit_collection(collection, self.branch, msg)


class CollectionRepo(GitRepo):
    """Representation of a datalad collection repository.

    A Collection is represented as a git-repository containing:
        a) a file named 'collection', which stores metadata of the collection
           itself, and
        b) one file per handle, storing the metadata of each handle

    Attention: files are valid only if in git.
    Being present is not sufficient!
    """

    # TODO: Change to two files per handle/collection:
    # 'collection' and ${key2filename} with ids, names, default layout
    # and a directory 'metadatacache' containing, again, one file per each item

    # TODO: collection level metadata; include statement
    # (self.get_uri_ref(), RDF.type, DLNS.Collection)
    # But: get_uri_ref: How to distinct branches? Just '/branch'?

    __slots__ = GitRepo.__slots__ + ['name']

    def __init__(self, path, url=None, name=None, runner=None):
        """

        Parameters:
        -----------
        path: str
          path to git repository. In case it's not an absolute path, it's
          relative to os.getcwd()

        url: str
          url to the to-be-cloned repository. Requires valid git url
          according to
          http://www.kernel.org/pub/software/scm/git/docs/git-clone.html#URLS .

        name: str
          optional name of the collection. This is only used for creating new
          collections. If there is a collection repo at path already, `name`
          is ignored.

        Raises:
        -------
        CollectionBrokenError
        """

        super(CollectionRepo, self).__init__(path, url, runner=runner)

        if not self.get_indexed_files():
            # it's a brand new collection repo.

            # default name is the name of the directory, this repository is
            # located in.
            self.name = name if name else basename(self.path)

            # create collection file
            # How to name that file? For now just 'collection'
            #  generally contains:
            #   - default layout on filesystem?
            #     (Q: implicitly requires a list of handles?
            #      This would give an additional consistency check)
            with open(opj(self.path, 'collection'), 'w') as f:
                f.write("New collection: %s" % self.name)
            self.git_add('collection')
            self.git_commit("Collection initialized.")

        elif 'collection' not in self.get_indexed_files():
            raise CollectionBrokenError("Missing file: 'collection'.")

        else:
            # may be read the collection file/handle infos
            # or may be do it on demand?
            with open(opj(self.path, 'collection'), 'r') as f:
                self.name = f.readline()[18:]

            # For now read a list of handles' names, ids, paths and metadata
            # as a proof of concept:
            # self._update_handle_data()

    def _filename2key(self, fname):
        """Placeholder

        For now just returns input.
        """
        return fname

    def _key2filename(self, key):
        """Placeholder

        For now just returns input.
        """
        return key

    def get_metadata(self, branch):
        # TODO: need collection-level metadata
        # Also rethink the next two methods

        # May a) get the metadata of a who9le branch including collection-level
        # and b) get the same for all branches => metacollection
        # But: What exactly to return, since the collection should manage the store?
        # Does it? Returning the dictionary is needed either way.
        pass

    def get_handles_data(self, branch='HEAD'):
        """Get the metadata of all handles in `branch`.

        Returns:
        --------
        dictionary

        """
        out = dict()

        # load handles from branch
        for filename in self.git_get_files(branch):
            if filename != 'collection':
                for line in self.git_get_file_content(filename, branch):
                    if line.startswith("handle_id = "):
                        id_ = line[12:]
                    elif line.startswith("last_seen = "):
                        url = line[12:]
                    elif line.startswith("metadata = "):
                        md = line[11:]
                    else:
                        md += line
                # TODO: dict instead of tuple:
                out[self._filename2key(filename)] = (id_, url, md)
        return out

    def get_remotes_data(self, name=None):
        """Get the metadata of all remotes.

        Returns:
        --------
        dictionary
        """

        remotes = dict()

        # TODO: name! None->all

        for remote in self.git_get_remotes():
            remote_dict = remotes.get(remote, {})
            head_branch = None
            for remote_branch in self.git_get_remote_branches():
                head = re.findall(r'-> (.*)', remote_branch)

                if len(head):
                    # found the HEAD pointer
                    head_branch = head[0]
                    continue

                # TODO: By now these branches are named 'remote/branch';
                # correct for get_handles_data, but not in dict-representation,
                # so split and integrate outer loop.
                remote_dict[remote_branch] = \
                    self.get_handles_data(remote_branch)
            # Add entry 'HEAD':
            remote_dict['HEAD'] = remote_dict[head_branch]
            remotes[remote] = remote_dict

        return remotes

    def commit_collection(self, collection, branch='HEAD',
                          msg="Collection saved."):
        # TODO: branch is not used yet.

        if not isinstance(collection, Collection):
            raise TypeError("Can't save non-collection type: %s" %
                            type(collection))

        # save current branch and switch to the one to be changed:
        current_branch = self.git_get_active_branch()
        self.git_checkout(branch)

        # handle we no longer have
        no_more = set(self.get_indexed_files()).difference(
            [self._key2filename(k) for k in collection.keys()])
        for gone in no_more:
            # collection meta data is treated differently
            # TODO: Actually collection meta data isn't treated yet at all!
            if gone != 'collection':
                self.git_remove(gone)

        # update everything else to be safe
        files_to_add = []
        for k, v in collection.iteritems():
            with open(opj(self.path, self._key2filename(k)), 'w') as ofile:
                ofile.write('\n'.join(['%s = %s' % (cat, val)
                                      for cat, val in zip(('handle_id',
                                                           'last_seen',
                                                           'metadata'), v)]))
            files_to_add.append(self._key2filename(k))

        self.git_add(files_to_add)
        self.git_commit(msg)

        # restore repo's active branch on disk
        self.git_checkout(current_branch)

    def add_handle(self, handle, name=None):
        """Adds a handle to the collection repository.

        Parameters:
        -----------
        handle: HandleRepo
          For now, this has to be a locally available handle.
        name: str
          name of the handle. This is required to be unique with respect to the
          collection.
        """

        # default name of the handle:
        if not name:
            name = basename(handle.path)

        # Writing plain text for now. This is supposed to change to use
        # rdflib or sth.
        with open(opj(self.path, self._key2filename(name)), 'w') as f:
            f.write("handle_id = %s\n" % handle.datalad_id)
            f.write("last_seen = %s\n" % handle.path)
            f.write("metadata = %s\n" % handle.get_metadata().serialize())
            # what else? maybe default view or sth.

        # TODO: write to collection file:
        # entry for default layout?

        self.git_add(name)
        self.git_commit("Add handle %s." % name)

    def remove_handle(self, key):

        # TODO: also accept a HandleRepo instead of a name
        # TODO: remove stuff from collection file (if there is going to be any)
        self.git_remove(self._key2filename(key))
        self.git_commit("Removed handle %s." % key)

    def get_handles(self):
        handles_data = self.get_handles_data()
        return [HandleRepo(handles_data[x][1]) for x in handles_data]

    def get_handle(self, name):
        return HandleRepo(self.get_handles_data()[name][1])

    # Reintroduce:
    # TODO: Delay and wait for checking rdflib
    def update_meta_data_cache(self, handle):

        # TODO: All handles?

        # if isinstance(handle, basestring):
        #     key = handle
        # elif isinstance(handle, HandleRepo):
        #     key = handle.name
        # else:
        #     raise TypeError("can't update from handle given by %s (%s)." %
        #                     (handle, type(handle)))


        # with open(opj(self.path, self._key2filename(handle)), 'w') as f:

        pass

    def get_backend_from_branch(self, branch='HEAD'):
        return CollectionRepoBranchBackend(self, branch)


