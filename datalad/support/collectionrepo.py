# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Implements datalad collection repositories.
"""

import logging
import os
from os.path import join as opj, basename, split as ops, exists
from ConfigParser import SafeConfigParser

from rdflib import Graph, URIRef

from .gitrepo import GitRepo, _remove_empty_items
from .handlerepo import HandleRepo
from .handle import Handle, HandleBackend
from .exceptions import CollectionBrokenError
from .collection import Collection, CollectionBackend
from .metadatahandler import CustomImporter, DLNS, RDFS, Literal, \
    MetadataImporter, DCTERMS, RDF
from ..utils import assure_dir

lgr = logging.getLogger('datalad.collectionrepo')


class CollectionRepoBranchHandleBackend(HandleBackend):
    """HandleBackend for collection repositories.

    Implements a HandleBackend retrieving its data from a branch of a
    collection repository. This is a read-only backend for Handle, since a
    collection only contains a cache of the metadata of handles.
    """
    # TODO: raise proper Exceptions on write access
    # TODO: Better name of these classes

    def __init__(self, repo, branch, key):
        self.repo = repo
        self.branch = branch
        self.key = key
        self.cache = dict()
        self.update()

    def update(self):
        """Reloads data from git.

        Calls to backend interface methods return cached data.
        TODO: Maybe make an explicit update() mandatory for backends.
        """
        filename = self.repo._key2filename(self.key)

        # We need an object with readline() to parse:
        # TODO: More testing and may be provide this one outside, if successful
        class ParseableListOfLines(object):
            def __init__(self, listOfLines):
                self.content = listOfLines
                self.it = iter(self.content)

            def readline(self):
                try:
                    return self.it.next()
                except StopIteration:
                    return ''

        file_ = ParseableListOfLines(
            self.repo.git_get_file_content(filename, self.branch))
        cfg = SafeConfigParser()
        cfg.readfp(file_)

        self.cache['id'] = cfg.get('Handle', 'id')
        self.cache['last_seen'] = cfg.get('Handle', 'last_seen')

        # TODO: See CollectionRepo.get_collection()
        path = self.repo._get_cfg('Collection', 'cache_path')
        handler = CacheHandler(path, URIRef(self.cache['last_seen']))
        self.cache['meta'] = handler.get_graph(
            identifier=self.key,
            data=self.repo.git_get_file_content(opj(path, filename),
                                                self.branch))

    @property
    def id(self):
        return self.cache['id']

    @property
    def url(self):
        return self.cache['url']

    def get_name(self):
        return self.key

    def set_name(self, name):
        lgr.warning("Can't write handle data from within %s" +
                    str(self.__class__))

    name = property(get_name, set_name)

    def get_metadata(self):
        return self.cache['meta']

    def set_metadata(self, meta):
        lgr.warning("Can't write handle data from within %s" +
                    str(self.__class__))

    metadata = property(get_metadata, set_metadata)


class CollectionRepoBranchBackend(CollectionBackend):
    """CollectionBackend for collection repositories.

    Implements a CollectionBackend that is connected to a branch of collection
    repository.
    """
    # TODO: Better name

    # Note (reminder): If it's a remote branch: Should writing data imply a
    # push or sth.?
    # Probably not, but it should be well documented, since 'saving' a
    # collection with a remote url and then it's just locally done, could be
    # confusing to users not familiar with git.
    # To be worked out when implementing such commands.

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

        self.branch = branch

    def get_handles(self):
        # TODO: implement the shit herein instead of CollectionRepo
        return self.repo.get_handles(self.branch)

    def get_collection(self):
        # TODO: implement the shit herein instead of CollectionRepo
        return self.repo.get_collection(self.branch)

    def commit_collection(self, collection, msg):
        # TODO: implement the shit herein instead of CollectionRepo
        self.repo.commit_collection(collection, self.branch, msg)


class CollectionRepo(GitRepo):
    """Representation of a datalad collection repository.

    A Collection is represented as a git-repository containing:
        a) a file named 'collection', which stores metadata of the collection
           itself, and
        b) one file per handle, storing the metadata of each handle

    Attention: files are valid only if in git.
    Being present is not sufficient!

    Note: new file layout for collection repositories:
    ./                one cfg-file per handle, plus collection.cfg
    ./metadatacache/  one rdf-file per handle
    ./collection/     collection-level metadata
    """

    # TODO: Collection level metadata:
    #       - get/set like for handles
    #       - include statement (self.get_uri_ref(), RDF.type, DLNS.Collection)
    #         But: get_uri_ref: How to distinct branches? Just '/branch'?

    # TODO: not up-to-date:
    # __slots__ = GitRepo.__slots__ + ['name']

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

        self._cfg_file = 'config.ttl'
        self._md_file = 'datalad.ttl'

        importer = CustomImporter('Collection', 'Collection', DLNS.this)
        # load existing files:
        if self._cfg_file in self.get_indexed_files():
            importer.import_data(opj(self.path, self._cfg_file))
        if self._md_file in self.get_indexed_files():
            importer.import_data(opj(self.path, self._md_file))
        graphs = importer.get_graphs()

        # collection settings:
        # if there is no name statement, add it:
        if len([subj for subj in graphs['config'].objects(DLNS.this,
                                                          RDFS.label)]) == 0:
            graphs['config'].add((DLNS.this, RDFS.label,
                                  Literal(name or basename(self.path))))

        importer.set_graphs(graphs)  # necessary?
        importer.store_data(self.path)
        # TODO: How do we know something has changed?
        # => check git status?
        self.git_add([self._cfg_file, self._md_file])
        self.git_commit("Initialized config file.")

    def _get_cfg(self):
        config_handler = CustomImporter('Collection', 'Collection', DLNS.this)
        config_handler.import_data(opj(self.path, self._cfg_file))
        return config_handler.get_graphs()['config']

    def _set_cfg(self, graph, commit_msg="Updated config file."):
        config_handler = CustomImporter('Collection', 'Collection', DLNS.this)
        graph_dict = dict()
        graph_dict['config'] = graph
        config_handler.set_graphs(graph_dict)
        config_handler.store_data(self.path)
        self.git_add(self._cfg_file)
        self.git_commit(commit_msg)

    # TODO: Consider using preferred label for the name
    def get_name(self):
        return [x for x in self._get_cfg().objects(DLNS.this, RDFS.label)][0]

    def set_name(self, name):
        graph = self._get_cfg()
        for old_name in graph.objects(DLNS.this, RDFS.label):
            graph.remove(DLNS.this, RDFS.label, old_name)
        graph.add(DLNS.this, RDFS.label, Literal(name))

    name = property(get_name, set_name)

    def _get_handle_files(self, branch="HEAD"):
        """Get a list of the handle files in `branch`
        """
        # Invalid:
        #return [ops(f)[1] for f in self.git_get_files(branch)
        #        if ops(f)[0] == '' and ops(f)[1] != self._cfg_file]

        raise NotImplementedError

    def get_handle_list(self, branch=None):
        """Get a list of the names of the handles in `branch`

        If `branch` is not provided, the active one is used.
        """
        return [self._filename2key(f, branch)
                for f in self._get_handle_files(branch)]

    def set_metadata_handler(self, handler):
        """Set the handler for collection-level metadata
        """
        #if not issubclass(handler, MetadataHandler):
        #    raise TypeError("%s is not a MetadataHandler." % type(handler))

        #self._set_cfg('Metadata', 'handler', handler.__name__)
        raise NotImplementedError

    # ### helper functions:

    def get_metadata_handler(self):
        """Helper to return the correct class of the metadata handler
        """
        # TODO: Add this one also to handlerepo
        # name = self._get_cfg('Metadata', 'handler')
        # import datalad.support.metadatahandler as mdh
        # try:
        #     handler = getattr(mdh, name)
        # except AttributeError:
        #     lgr.error("'%s' is an unknown metadata handler." % name)
        #     raise ValueError("'%s' is an unknown metadata handler." % name)
        # return handler
        raise NotImplementedError

    def _filename2key(self, fname, branch):
        """Placeholder

        This transformation of a filename to a handle's key may change.
        """

        return self.name + '/' + branch + '/' + fname

    def _key2filename(self, key):
        """Placeholder

        This transformation of a handle's key to a filename may change.
        """
        # TODO: Rethink whether ignoring the collection/branch part
        # is appropriate herein.
        return _remove_empty_items(key.split('/'))[-1:][0]

    # ### repo methods:

    # TODO: add and remove are inconsistent in use of name/key of a handle;
    # Will figure out, what's needed while writing the test cases:


    def get_handle_repos(self, branch=None):
        """Get a list of HandleRepo instances.

        Returns a list containing HandleRepo instances representing locally
        available handle repositories, that are part of the collection
        in `branch`. If no branch is given, the active branch is used.
        """
        repo_list = []
        for handle in self._get_handle_files(branch):
            parser = SafeConfigParser()
            parser.read(opj(self.path, handle))
            path = parser.get('Handle', 'last_seen')
            if exists(path):
                repo_list.append(HandleRepo(path))
        return repo_list

    def get_handle_repo(self, key):
        """Get a HandleRepo instance for handle `key`.

        If the handle isn't locally available, returns None.
        """
        # TODO: branch-option?
        parser = SafeConfigParser()
        parser.read(opj(self.path, self._key2filename(key)))
        path = parser.get('Handle', 'last_seen')
        if exists(path):
            return HandleRepo(path)
        else:
            return None

    def update_meta_data_cache(self, key=None):
        """Rewrite the collection's metadata cache.
        """
        files = self._get_handle_files() if key is None \
            else [self._key2filename(key)]

        for handle_file in files:
            cfg = SafeConfigParser()
            cfg.read(opj(self.path, handle_file))
            handle_path = cfg.get('Handle', 'last_seen')

            # update from locally available handles only:
            if exists(handle_path):
                repo = HandleRepo()
                CacheHandler(opj(self.path,
                                 self._get_cfg('Metadata', 'cache_path')),
                             URIRef(repo.path)).set(repo.get_metadata(),
                                                    handle_file)

    # ### Implementation of collection backend:

    def get_collection(self, branch=None):
        """Get collection level metadata of a branch
        """
        out = dict()
        if branch is None:
            branch = self.git_get_active_branch()
        out['name'] = self.name + '/' + branch

        # TODO: Rework the following to be able to get the content
        # of the whole directory and pass it to the handler. This is vital, but
        # for the proof of concept somewhat ignore the handler concept and
        # assume a single file with a certain name.
        # Note: Same counts for handle backend
        path = self._get_cfg('Metadata', 'path')
        filename = 'metadata.rdf'
        handler = self.get_metadata_handler()(opj(self.path, path), URIRef(self.path))
        out['meta'] = handler.get_graph(identifier=out['name'],
                                        data=self.git_get_file_content(
                                            opj(path, filename), branch))
        return out

    # May be a getHandles(class), returning a list of class instead?
    def get_handles(self, branch=None):
        """Get the metadata of all handles in `branch`.

        Returns:
        --------
        dictionary of Handle

        """
        out = dict()
        if branch is None:
            branch = self.git_get_active_branch()

        # load handles from branch
        for key in self.get_handle_list(branch):
            out[key] = Handle(src=CollectionRepoBranchHandleBackend(
                self, branch, key))
        return out

    def commit_collection(self, collection, branch=None,
                          msg="Collection saved."):

        if not isinstance(collection, Collection):
            raise TypeError("Can't save non-collection type: %s" %
                            type(collection))

        # save current branch ...
        current_branch = self.git_get_active_branch()

        if branch is None:
            branch = current_branch

        if branch != current_branch:
            # ... and switch to the one to be changed:
            self.git_checkout(branch)

        # handle files we no longer have:
        no_more = set([ops(f)[1] for f in self.get_indexed_files()
                       if ops(f)[0] == '']).difference(
            [self._key2filename(k) for k in collection.keys()])
        no_more.remove(self._cfg_file)  # not a handle file

        files_to_remove = []
        for gone in no_more:
            files_to_remove.extend([gone,
                                    opj(self._get_cfg('Collection',
                                                      'cache_path'),
                                        gone)])
        self.git_remove(files_to_remove)

        # update everything else to be safe
        files_to_add = []
        for k, v in collection.iteritems():
            cfg = SafeConfigParser()
            cfg.read(opj(self.path, self._key2filename(k)))
            cfg.set('Handle', 'id', v.id)
            cfg.set('Handle', 'last_seen', v.url)
            # TODO: Do we need 'default_target' in Handle?
            cfg.write(open(opj(self.path, self._key2filename(k)), 'w'))
            files_to_add.append(self._key2filename(k))

            # write metadata cache:
            CacheHandler(opj(self.path,
                             self._get_cfg('Collection', 'cache_path')),
                         URIRef(v.url)).set(v.meta, self._key2filename(k))
            files_to_add.append(opj(self._get_cfg('Collection', 'cache_path'),
                                    self._key2filename(k)))

        # write collection files:
        CacheHandler(opj(self.path,
                         self._get_cfg('Collection', 'cache_path')),
                     URIRef(self.path)).set(collection.meta, 'collection')
        files_to_add.append(opj(self._get_cfg('Collection', 'cache_path'),
                                'collection'))
        self.git_add(files_to_add)
        self.git_commit(msg)

        self.name = collection.name

        if branch != current_branch:
            # switch back to repo's active branch on disk
            self.git_checkout(current_branch)

    def get_backend_from_branch(self, branch=None):
        """Convenience function to get a backend from a branch of this repo.

        By default a backend to the active branch is returned.
        """
        if branch is None:
            branch = self.git_get_active_branch()
        return CollectionRepoBranchBackend(self, branch)

    # #######################################
    # TODO (adapting to new design):
    # add/remove handle
    # add metadata sources
    # adapting backends and may be Handle/Collection interfaces
    # test cases
    # update metadata sources
    # remove metadata sources ?

    def add_metadata_src_to_handle(self, importer, key, files=None,
                                   data=None):
        """Imports a new metadata source

        Parameters:
        ___________
        importer: class
          the importer to be used; has to be a subclass of MetadataImporter
        key: str
          the handle's key in the collection
        files: str or list of str
          either a path to the file or directory to be imported or a list
          containing paths to the files.
        data: dict of list of str
          a dictionary containing the metadata to be imported. The key is
          expected to be the file name and the value its content as a list of
          the file's lines as returned by `readlines()`.
        """

        if not issubclass(importer, MetadataImporter):
            raise TypeError("Not a MetadataImporter: " + str(importer))

        handle = CollectionRepoBranchHandleBackend(
            self, self.git_get_active_branch(), key)
        handle_cfg = handle.get_metadata('config')

        # TODO: CollectionRepoBranchHandleBackend.get_metadata('config')

        # check for existing metadata sources to determine the name for the
        # new one:
        src_name = "%s_import%d" % (key,
                                    len([src for src in
                                         handle_cfg.objects(URIRef(handle.url),
                                                            DLNS.usesSrc)])
                                    + 1)

        im = importer(target_class='Collection', about_class='Handle',
                      about_uri=URIRef(handle.url), name=src_name)
        # => TODO: add this 'name'-parameter and write handle-config in importer class!
        im.import_data(files=files, data=data)

        # create import branch:
        active_branch = self.git_get_active_branch()
        self.git_checkout(name=src_name, options='-b')

        im.store_data(opj(self.path, self._key2filename(key)))
        self.git_commit("New import branch created.")

        # switching back and merge:
        self.git_checkout(active_branch)
        self.git_merge(ref=src_name)  # TODO!

    # TODO: following methods similar to 'add_metadata_src_to_handle'
    def add_metadata_src_to_collection(self):
        raise NotImplementedError

    def add_metadata_src_to_entity(self):
        # But: also needs handle or collection
        # So may be add parameters to the other methods for importing data
        # about a sub-entity instead of an dedicated method for that.
        raise NotImplementedError

    def add_handle(self, handle, name):
        """Adds a handle to the collection repository.

        Parameters:
        -----------
        handle: str or HandleRepo or HandleBackend
          URL of the handle or an instance of either HandleRepo or HandleBackend.
        name: str
          name of the handle within the collection. This name is required to be
          unique with respect to the collection. If a HandleRepo or
          HandleBackend is passed, the name stored therein is the default.
          If `handle` is just an URL, a name is required.
        """
        if isinstance(handle, HandleBackend):
            uri = URIRef(handle.url)
            name = name or handle.name

        if isinstance(handle, HandleRepo):
            uri = URIRef(handle.path)
            name = name or handle.name

        if isinstance(handle, basestring):
            uri = URIRef(handle)
            if name is None:
                raise ValueError("Argument 'name' is None.")

        # TODO: What about branch? For now, just active one.
        # This means, the branch to add the handle to, has to be checked out.
        # Is there a point in providing anything else?
        branch = self.git_get_active_branch()
        key = self.name + '/' + branch + '/' + name

        path = opj(self.path, self._key2filename(key))
        # TODO: What's the desired behaviour in case a handle with that name
        # already exists?
        if exists(path):
            raise RuntimeError("Handle '%s' already exists." % name)
        os.mkdir(path)

        md_handle = CustomImporter(target_class='Collection',
                                   about_class='Handle',
                                   about_uri=uri)
        graphs = md_handle.get_graphs()

        # handle config:
        # default name:
        graphs['config'].add((uri, RDFS.label, Literal(name)))
        # default dir name:
        graphs['config'].add((uri, DLNS.defaultTarget, Literal(name)))
        # TODO: anything else?
        md_handle.set_graphs(graphs)
        md_handle.store_data(path)

        # collection graph:
        # TODO: helper functions
        md_collection = CustomImporter(target_class='Collection',
                                       about_class='Collection',
                                       about_uri=DLNS.this)
        md_collection.import_data(self.path)
        graphs = md_collection.get_graphs()
        graphs['datalad'].add((DLNS.this, DCTERMS.hasPart, uri))
        # TODO: anything else? any config needed?
        md_collection.set_graphs(graphs)
        md_collection.store_data(self.path)

        self.git_add([opj(self.path, 'datalad.ttl'),
                      opj(path, 'config.ttl')])
        self.git_commit("Added handle '%s'" % name)

    def remove_handle(self, key):

        dir_ = self._key2filename(key)

        # remove handle from collection descriptor:
        uri = Graph().parse(opj(dir_, 'datalad.ttl')).value(predicate=RDF.type,
                                                            object=DLNS.Handle)
        col_graph = Graph().parse(opj(self.path, 'datalad.ttl'))
        col_graph.remove((DLNS.this, DCTERMS.hasPart, uri))
        col_graph.serialize(opj(self.path, 'datalad.ttl'), format="turtle")

        # remove handle's directory:
        # TODO: delete it or only git rm?
        self.git_remove(dir_)
        self.git_commit("Removed handle %s." % key)


    # old stuff; just outcommented for now:
    # def get_remotes_data(self, name=None):
    #     """Get the metadata of all remotes.
    #
    #     Returns:
    #     --------
    #     dictionary
    #     """
    #
    #     remotes = dict()
    #
    #     # TODO: name! None->all
    #
    #     for remote in self.git_get_remotes():
    #         remote_dict = remotes.get(remote, {})
    #         head_branch = None
    #         for remote_branch in self.git_get_remote_branches():
    #             head = re.findall(r'-> (.*)', remote_branch)
    #
    #             if len(head):
    #                 # found the HEAD pointer
    #                 head_branch = head[0]
    #                 continue
    #
    #             # TODO: By now these branches are named 'remote/branch';
    #             # correct for get_handles_data, but not in dict-representation,
    #             # so split and integrate outer loop.
    #             remote_dict[remote_branch] = \
    #                 self.get_handles_data(remote_branch)
    #         # Add entry 'HEAD':
    #         remote_dict['HEAD'] = remote_dict[head_branch]
    #         remotes[remote] = remote_dict
    #
    #     return remotes

    # def add_handle(self, handle, name=None):
    #     """Adds a handle to the collection repository.
    #
    #     Parameters:
    #     -----------
    #     handle: HandleRepo
    #       For now, this has to be a locally available handle.
    #     name: str
    #       name of the handle. This is required to be unique with respect to the
    #       collection.
    #     """
    #     # TODO: What about branch? For now, just active one.
    #     # This means, the branch to add the handle to, has to be checked out.
    #     # Is there a point in providing anything else?
    #     branch = self.git_get_active_branch()
    #
    #     # default name of the handle:
    #     if not name:
    #         name = handle.name
    #
    #     key = self.name + '/' + branch + '/' + name
    #     filename = self._key2filename(key)
    #
    #     # old:
    #     # cache_path = self._get_cfg('Collection', 'cache_path')
    #     # incomplete adaption:
    #     cache_path = opj(self.path, filename)
    #
    #     # create the handle's config file:
    #     cfg = SafeConfigParser()
    #     cfg.add_section('Handle')
    #     # Again, not sure yet, whether this id is needed:
    #     cfg.set('Handle', 'id', handle.datalad_id)
    #     # 'last_seen' for now holds the local path;
    #     # to be replaced by an url on publishing for example:
    #     cfg.set('Handle', 'last_seen', handle.path)
    #     # default installation dir beneath the collection dir,
    #     # holding it's handles:
    #     cfg.set('Handle', 'default_target', name)
    #
    #     with open(opj(self.path, filename), 'w') as f:
    #         cfg.write(f)
    #
    #     # metadata cache:
    #     handler = CacheHandler()
    #     handler.set(handle.get_metadata(), opj(self.path, cache_path,
    #                                            filename))
    #
    #     self.git_add([opj(cache_path, filename), filename])
    #     self.git_commit("Added handle %s." % name)
    # def remove_handle(self, key):
    #
    #     filename = self._key2filename(key)
    #     cache_path = self._get_cfg('Collection', 'cache_path')
    #     self.git_remove([opj(cache_path, filename), filename])
    #     self.git_commit("Removed handle %s." % key)
