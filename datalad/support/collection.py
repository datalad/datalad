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
import logging

from rdflib import Graph, URIRef, Namespace
from rdflib.namespace import RDF

from .gitrepo import GitRepo
from .handle import Handle
from .exceptions import CollectionBrokenError

# define datalad namespace:
DLNS = Namespace('http://www.datalad.org/terms/')

lgr = logging.getLogger('datalad.collection')

# TODO: Add/remove for Collections and MetaCollections.
# Collection => done. It's a dictionary.
# So, let a meta collection be a dictionary of collections?
# Actually, that way the meta data isn't updated. So, add/remove handle
# probably still necessary.
#
# => just override __setitem__ and __delitem__!

class MetaCollection(object):
    """ Needs a better name;
        Provides all (remote) branches of a collection repository.
        May be could serve as a meta collection in general (let's see how
        this works out).
    """

    # TODO: There is a ConjunctiveGraph in rdflib! May be use this one? Or the Dataset?


    def __init__(self, src=None):

        # - a list of collection backends? or no backend at all? Let the Collections care for it.
        # - a list of collections
        # - another MetaCollection
        # -

        if isinstance(src, CollectionRepo):
            self._repo = src

            # TODO: May be don't separate local and remote branches,
            # but use "remote/branch" as key, which is the branches name anyway.
            # For THE local master collection we may be need instead to somehow
            # differentiate locally available remotes and actually remote
            # remotes of the repository.

            self.local_collections = dict()
            for branch in src.git_get_branches():  # TODO: 'HEAD' missing.
                self.local_collections[branch] = Collection(src=self._repo,
                                                            branch=branch)

            self.remote_collections = self._repo.get_remotes_data()

            # TODO: load and join the metadata ...:
            # to be refined; For now just join everything as is, to see how this works.
            # Reminder: Joining different branches probably won't work as is.
            # Especially there is the question of how to reconstruct the branch, we found something in?
            self.huge_graph = Graph()
            for collection in self.local_collections:
                self.huge_graph +=self.local_collections[collection].meta
            for collection in self.remote_collections:
                for branch in self.remote_collections[collection]:
                    self.huge_graph += self.remote_collections[collection][branch].meta

        else:
            lgr.error('Unknown source for MetaCollection(): %s' % type(src))
            raise TypeError('Unknown source for MetaCollection(): %s' % type(src))

    def update(self, remote=None, branch=None):
        # reload (all) branches
        pass

    def query(self):
        """ Perform query on (what?) collections.

        Returns:
        --------
        list of handles? (names => remote/branch/handle?)
        """


class Collection(dict):
    # TODO: For now it represents just a branch of a collection repo with
    # no access to other branches. But then it has (kind of) "remotes"
    # including all of their branches. This is not exactly consistent.
    # So we should either make all branches of the repo itself available as
    # well or remove the remotes, let a Collection represent a single branch
    # and let a repository represent a "Meta-Collection".

    # Note: Agreed with Michael, to have a collection per (remote) branch.
    # local Master collection knows a lot of them and somehow joins rdf-metadata
    # to big db, which is used for queries.

    def __init__(self, src=None):

        super(Collection, self).__init__()

        if isinstance(src, Collection):
            self._backend = None
            # TODO: confirm this is correct behaviour and document it.

            self.update(src)
            # XXX most likely a copy
            self.meta = src.meta
        elif isinstance(src, CollectionBackend):
            self._backend = src
            self._reload()
        elif src is None:
            self._backend = None
            self.meta = Graph()
        else:
            lgr.error("Unknown source for Collection(): %s" % type(src))
            raise TypeError('Unknown source for Collection(): %s' % type(src))

        # TODO: Collection has a store, containing named graphs for all handles
        # plus one for itself. So, empty source means: store with the empty,
        # named graph of the collection.
        # if source is another collection: this has to be a copy of the whole store.
        # => copy.deepcopy()


    def _reload(self):
        if not self._backend:
            lgr.warning("_reload(): Missing repository.")
            return

        self.update(self._backend.get_collection_data())
        self.meta = Graph()

        # Create node for collection itself:
        collection_node = self._backend.get_uri_ref()
        self.meta.add((collection_node, RDF.type, DLNS.Collection))

        for handle in self:
            try:
                # TODO: Ask backend here. And add named graph to collection's store.
                # => is this "reload" at all? Yes. self.update() did the job above.
                handle_graph = Graph().parse(data=self[handle][2])
            except Exception, e:
                lgr.error("Data:\n%s" % self[handle][2])
                raise e
            # join the handle's graph into the collection's one and connect
            # collection node to handle node:
            handle_node = handle_graph.value(predicate=RDF.type, object=DLNS.Handle)
            self.meta += handle_graph
            self.meta.add((collection_node, DLNS.contains, handle_node))

    def query(self):
        # Not sure yet whether we need to have a query
        # on a single Collection instance.
        pass

    def commit(self, msg="Cheers!"):

        if not self._backend:
            lgr.error("commit(): Missing collection backend.")
            raise RuntimeError("commit(): Missing collection backend.")

        self._backend.commit_collection(self, msg)


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
        handle: Handle
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

        # TODO: also accept a Handle instead of a name
        # TODO: remove stuff from collection file (if there is going to be any)
        self.git_remove(self._key2filename(key))
        self.git_commit("Removed handle %s." % key)

    def get_handles(self):
        handles_data = self.get_handles_data()
        return [Handle(handles_data[x][1]) for x in handles_data]

    def get_handle(self, name):
        return Handle(self.get_handles_data()[name][1])

    # Reintroduce:
    # TODO: Delay and wait for checking rdflib
    def update_meta_data_cache(self, handle):

        # TODO: All handles?

        # if isinstance(handle, basestring):
        #     key = handle
        # elif isinstance(handle, Handle):
        #     key = handle.name
        # else:
        #     raise TypeError("can't update from handle given by %s (%s)." %
        #                     (handle, type(handle)))


        # with open(opj(self.path, self._key2filename(handle)), 'w') as f:

        pass

    def get_backend_from_branch(self, branch='HEAD'):
        return CollectionRepoBranchBackend(self, branch)

from abc import ABCMeta, abstractmethod, abstractproperty


class CollectionBackend(object):
    # How to pass the branch (especially on reload) without the collection
    # knowing anything about branches? => Let the backend store it. But then we
    # different backend instances for the same repo.
    # => 'name'; just treat it as a name, the backend is asked for.


    # get_handles_data(name('branch')) => get_collection_data?

    # + get_all_collection_data()?

    # get_uri_ref('name')? => path (or url of remotes?), what about single branches?

    # get_name()

    # commit_collection('name')
    # => name: problem: if it designates a branch what's its uri?
    #                   additionally: What about the metacollection then?
    #                   The latter represents the repo as a whole, so should have
    #                   the repos uri. But a single branch? Just 'collectionname/branch'?


    # CollectionRepo returns a backend-instance (per branch), so that object knows,
    # how to query the repo. No, let's treat it as a store, ask for a collection's
    # data by name. => Collection has to know that name (corresponds to the branch)


    # may be even better: Just two methods:
    #                     - get collection data (including uri, name) as dict => src
    #                     - store data (name) => branch's name is extracted by CollectionRepo itself
    #                      -> no 'backend' at all? But needs that store/commit-method + reload?
    # => back to a backend instance provided by the repo (per branch)

    __metaclass__ = ABCMeta

    @abstractmethod
    def get_collection_data(self):
        """

        Returns:
        --------
        dictionary
        """
        pass

    @abstractmethod
    def get_uri_ref(self):
        pass

    @abstractmethod
    def commit_collection(self, collection, msg):
        """

        Parameters:
        -----------
        collection: Collection
        msg: str
        """


class CollectionRepoBranchBackend(CollectionBackend):
    # TODO: Better name

    def __init__(self, repo, branch='HEAD'):
        """
        Parameters:
        -----------
        repo: CollectionRepo
        branch: str
        """
        self.branch = branch
        self.repo = repo

    def get_collection_data(self):
        return self.repo.get_handles_data(self.branch)

    def get_uri_ref(self):
        # TODO: How to differentiate several branches here?
        return URIRef(self.repo.path)

    def commit_collection(self, collection, msg):
        self.repo.commit_collection(collection, self.branch, msg)
