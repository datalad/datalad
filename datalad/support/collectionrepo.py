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
from os.path import join as opj, basename, split as ops, exists, isdir
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


class CollectionRepoHandleBackend(HandleBackend):
    """HandleBackend for collection repositories.

    Implements a HandleBackend retrieving its data from a branch of a
    collection repository. This is a read-only backend for Handle, since a
    collection only contains a cache of the metadata of handles.
    """
    # TODO: raise proper Exceptions on write access
    # TODO: Better name of these classes
    # TODO: Update docs!

    def __init__(self, repo, key, branch=None):
        self.repo = repo
        self.branch = branch if branch is not None \
            else self.repo.git_get_active_branch()
        self.key = key
        self._path = self.repo._key2filename(self.key)
        self._cfg_file = opj(self._path, "config.ttl")
        self._std_file = opj(self._path, "datalad.ttl")

        # remote branch? => read-only
        if self.branch.split('/')[0] in self.repo.git_get_remotes():
            self.is_read_only = True
        else:
            self.is_read_only = False

    def get_metadata(self, files=None):
        """
        Gets metadata graph for the handle (all files in collection or just
        `files`)
        Parameters:
        -----------
        files: list of str

        Returns:
        --------
        rdflib.Graph
        """
        cfg_str = '\n'.join(self.repo.git_get_file_content(self._cfg_file,
                                                           self.branch))
        cfg_graph = Graph().parse(data=cfg_str, format="turtle")

        h_node = cfg_graph.value(predicate=RDF.type, object=DLNS.Handle)
        h_name = cfg_graph.value(subject=h_node, predicate=RDFS.label)

        # additional files in handle's dir:
        if files is None:
            files = [file_
                     for file_ in self.repo.git_get_files(branch=self.branch)
                     if file_.startswith(self.repo._key2filename(self.key))
                     and basename(file_) != "config.ttl"]

        out = Graph(identifier=h_name)
        for file_ in files:
            file_str = '\n'.join(self.repo.git_get_file_content(file_,
                                                                self.branch))
            out.parse(data=file_str, format="turtle")

        # Note: See note in CollectionRepoBackend.get_collection
        return out

    def set_metadata(self, meta, msg="Handle metadata updated."):

        if self.is_read_only:
            raise RuntimeWarning("Can't write to read-only handle.")

        # save current branch ...
        current_branch = self.repo.git_get_active_branch()

        if self.branch != current_branch:
            # ... and switch to the one to be changed:
            self.repo.git_checkout(self.branch)

        assure_dir(opj(self.repo.path, self._path))
        meta.serialize(self._std_file, format="turtle")
        self.repo.git_add(self._std_file)
        self.repo.git_commit(msg=msg)

        if self.branch != current_branch:
            self.repo.git_checkout(current_branch)

    @property
    def url(self):
        if self.is_read_only:
            # remote repo:
            cfg_str = '\n'.join(self.repo.git_get_file_content(self._cfg_file,
                                                               self.branch))
            cfg_graph = Graph().parse(data=cfg_str, format="turtle")
            return cfg_graph.value(predicate=RDF.type, object=DLNS.Handle)
        else:
            # available repo:
            return self.repo.path


class CollectionRepoBackend(CollectionBackend):
    """CollectionBackend for collection repositories.

    Implements a CollectionBackend that is connected to a branch of a
    collection repository.
    """
    # TODO: Better name

    # Note (reminder): If it's a remote branch: Should writing data imply a
    # push or sth.?
    # Probably not, but it should be well documented, since 'saving' a
    # collection with a remote url and then it's just locally done, could be
    # confusing to users not familiar with git.
    # To be worked out when implementing such commands.
    #
    # Better to not allow to commit to remote branches and force the user to
    # clone it first.

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

        self.branch = branch if branch is not None \
            else self.repo.git_get_active_branch()

        # remote branch? => read-only
        if self.branch.split('/')[0] in self.repo.git_get_remotes():
            self.is_read_only = True
        else:
            self.is_read_only = False

    def get_handles(self):
        """Get the metadata of all handles in `branch`.

        Returns:
        --------
        dictionary of Handle

        """
        out = dict()

        # load handles from branch
        for key in self.repo.get_handle_list(self.branch):
            out[key] = Handle(src=CollectionRepoHandleBackend(
                self.repo, key, self.branch))
        return out

    def get_collection(self):
        """Get collection level metadata of a branch
        """
        # read standard files:
        cfg_str = '\n'.join(self.repo.git_get_file_content("config.ttl",
                                                           self.branch))
        std = Graph().parse(data=cfg_str, format="turtle")

        col_node = std.value(predicate=RDF.type, object=DLNS.Collection)
        col_name = std.value(subject=col_node, predicate=RDFS.label)

        # additional files in collection's basedir:
        files = [file_ for file_ in self.repo.git_get_files(branch=self.branch)
                 if file_ == basename(file_) and file_ != "config.ttl"]

        out = Graph(identifier=col_name)  # avoid type 'URIRef' or sth.

        for file_ in files:
            file_str = '\n'.join(self.repo.git_get_file_content(file_,
                                                                self.branch))
            out.parse(data=file_str, format="turtle")

        # Note: By now we parse config.ttl and datalad.ttl two times here.
        # The issue is to determine the identifier of hte graph, which can't be
        # changed after creation. We probably also want to read certain files
        # only into the returned graph later on.

        return out

    def commit_collection(self, collection, msg):

        if self.is_read_only:
            raise RuntimeWarning("Can't commit remote collection.")

        if not isinstance(collection, Collection):
            raise TypeError("Can't save non-collection type: %s" %
                            type(collection))

        # save current branch ...
        current_branch = self.repo.git_get_active_branch()

        if self.branch != current_branch:
            # ... and switch to the one to be changed:
            self.repo.git_checkout(self.branch)

        # handle files we no longer have:
        files_to_remove = [f for f in self.repo.get_indexed_files()
                           if self.repo._filename2key(ops(f)[0]) not in
                           collection.keys()]

        self.repo.git_remove(files_to_remove)

        # update everything else to be safe
        files_to_add = []

        # collection level:
        collection.meta.serialize(opj(self.repo.path, self.repo._md_file),
                                  format="turtle")
        files_to_add.append(self.repo._md_file)

        # handles:
        for k, v in collection.iteritems():

            v.commit()
            # files_to_add.append(self.repo._key2filename(k))
            # Actually, this shouldn't be necessary, since it was
            # committed above. On the other hand, that's a lot of commits.
            # May be don't commit the handles but just write_to_file and commit
            # herein.

        self.repo.git_add(files_to_add)
        self.repo.git_commit(msg)

        if self.branch != current_branch:
            # switch back to repo's active branch on disk
            self.repo.git_checkout(current_branch)

    @property
    def url(self):
        if self.is_read_only:
            # remote repo:
            cfg_str = '\n'.join(self.repo.git_get_file_content("config.ttl",
                                                               self.branch))
            cfg_graph = Graph().parse(data=cfg_str, format="turtle")
            return str(cfg_graph.value(predicate=RDF.type,
                                       object=DLNS.Collection))
        else:
            # available repo:
            return self.repo.path


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

        if branch is None:
            branch = self.git_get_active_branch()

        # TODO: see _filename2key:
        # return set([self._filename2key(f.split(os.sep)[0], branch)
        #             for f in self.git_get_files(branch) if f != basename(f)])
        return set([f.split(os.sep)[0] for f in self.git_get_files(branch)
                    if f != basename(f)])

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

    def _filename2key(self, fname):
        """Placeholder

        This transformation of a filename to a handle's key may change,
        especially with respect to unicode keys.
        """
        # TODO: Check whether fname exists?
        return fname

    def _key2filename(self, key):
        """Placeholder

        This transformation of a handle's key to a filename may change.
        """
        parts = key.split('/')
        if len(parts) > 2 or len(parts) < 1:
            raise ValueError("Handle key '%s' invalid." % key)

        if len(parts) == 2 and parts[0] != str(self.name):
            # string cast needed for it possibly is a rdflib.Literal
            raise ValueError("Collection name '%s' doesn't "
                             "match active branch." % parts[0])
        return parts[-1]


    # ### repo methods:

    # TODO: add and remove are inconsistent in use of name/key of a handle;
    # Will figure out, what's needed while writing the test cases:

    def get_handle_repos(self, branch=None):
        """Get a list of HandleRepo instances.

        Returns a list containing HandleRepo instances representing locally
        available handle repositories, that are part of the collection
        in `branch`. If no branch is given, the active branch is used.
        """
        # repo_list = []
        # for handle in self._get_handle_files(branch):
        #     parser = SafeConfigParser()
        #     parser.read(opj(self.path, handle))
        #     path = parser.get('Handle', 'last_seen')
        #     if exists(path):
        #         repo_list.append(HandleRepo(path))
        # return repo_list
        raise NotImplementedError

    def get_handle_repo(self, key):
        """Get a HandleRepo instance for handle `key`.

        If the handle isn't locally available, returns None.
        """
        # TODO: branch-option?
        # parser = SafeConfigParser()
        # parser.read(opj(self.path, self._key2filename(key)))
        # path = parser.get('Handle', 'last_seen')
        # if exists(path):
        #     return HandleRepo(path)
        # else:
        #     return None
        raise NotImplementedError

    def get_backend_from_branch(self, branch=None):
        """Convenience function to get a backend from a branch of this repo.

        By default a backend to the active branch is returned.
        """
        if branch is None:
            branch = self.git_get_active_branch()
        return CollectionRepoBackend(self, branch)

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

        cfg_graph = Graph().parse(opj(self.path, self._key2filename(key),
                                      "config.ttl"), format="turtle")
        url = cfg_graph.value(predicate=RDFS.label, object=Literal(key))

        # check for existing metadata sources to determine the name for the
        # new one:
        src_name = "%s_import%d" % (key,
                                    len([src for src in
                                         cfg_graph.objects(url, DLNS.usesSrc)])
                                    + 1)
        src_node = URIRef(src_name)
        im = importer(target_class='Collection', about_class='Handle',
                      about_uri=url)
        im.import_data(files=files, data=data)

        # add config-entries for that source:
        cfg_graph.add((url, DLNS.usesSrc, src_node))
        # TODO: specify that source (used files, ..):
        # cfg_graph.add((src_node, ))

        # create import branch:
        active_branch = self.git_get_active_branch()
        self.git_checkout(name=src_name, options='-b')

        im.store_data(opj(self.path, self._key2filename(key)))
        cfg_graph.serialize(opj(self.path, self._key2filename(key),
                                "config.ttl"), format="turtle")
        self.git_add(self._key2filename(key))
        self.git_commit("New import branch created.")

        # switching back and merge:
        self.git_checkout(active_branch)
        self.git_merge(src_name)  # TODO!

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
            name = name or handle.get_metadata().identifier

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
        key = self.name + '/' + name

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

        self.git_add(['datalad.ttl', self._key2filename(key)])
        self.git_commit("Added handle '%s'" % name)

    def remove_handle(self, key):

        dir_ = self._key2filename(key)

        # remove handle from collection descriptor:
        uri = Graph().parse(opj(self.path, dir_, 'datalad.ttl'),
                            format="turtle").value(predicate=RDF.type,
                                                   object=DLNS.Handle)
        col_graph = Graph().parse(opj(self.path, 'datalad.ttl'),
                                  format="turtle")
        col_graph.remove((DLNS.this, DCTERMS.hasPart, uri))
        col_graph.serialize(opj(self.path, 'datalad.ttl'), format="turtle")

        # remove handle's directory:
        # Note: Currently all files separatly due to issues with the
        # normalize_path decorator in gitrepo.py. It expects one output per
        # one input file. So, recursively removing the 'dir_' violates that
        # assertion.
        [self.git_remove(file_) for file_ in self.get_indexed_files()
         if file_.startswith(dir_)]

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