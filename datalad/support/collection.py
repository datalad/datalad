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

from .gitrepo import GitRepo
from .handle import Handle
from .exceptions import CollectionBrokenError
from ..cmd import Runner

lgr = logging.getLogger('datalad.collection')


class Collection(dict):

    def __init__(self, src=None, branch='HEAD', load_remotes=False):

        super(Collection, self).__init__()
        self.remote_collections = None
        self._branch = branch
        self._load_remotes_flag = load_remotes

        if isinstance(src, Collection):
            self._colrepo = None
            self.update(src)
            # XXX most likely a copy
            self.meta = src.meta
        elif isinstance(src, CollectionRepo):
            self._colrepo = src
            self._reload()
        elif src is None:
            self._colrepo = None
            self.meta = 'rdf thingie later'
        else:
            raise TypeError('unknown source for Collection(): %s' % type(src))

    def _reload(self):
        if not self._colrepo:
            return

        self.update(self._load_handle_files(self._branch))

        if self._load_remotes_flag:
            self.remote_collections = self._load_remotes()

        self.meta = 'rdf thingie later'

    def _load_handle_files(self, branch):
        if not self._colrepo:
            return None

        return self._colrepo.get_handles(branch)

    def _load_remotes(self):
        if not self._colrepo:
            return None

        return self._colrepo.get_remotes_data()


    def query(self):
        pass

    def commit(self, branch=None, msg="Cheers!"):

        if not self._colrepo:
            raise RuntimeError("cannot commit -- have relationship issues")

        self._colrepo.save_collection(self, branch, msg)


class CollectionRepo(GitRepo):
    """Representation of a datalad collection.

    A Collection is represented as a git-repository containing:
        a) a file named 'collection', which stores metadata of the collection
           itself, and
        b) one file per handle, storing the metadata of each handle

    Attention: files are valid only if in git.
    Being present is not sufficient!
    """

    __slots__ = ['name']
    # TODO: check how __slots__ work with derived classes

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
        #self.handles = []

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

    def get_handles(self, branch):
        """Get the metadata of all handles.

        Returns:
        --------
        dictionary

        """
        out = {}

        # load handle from local branch
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
                        continue
                out[self._filename2key(filename)] = (id_, url, md)
        return out

    def get_remotes_data(self):
        """Get the metadata of all remotes.

        Returns:
        --------
        dictionary
        """

        remotes = dict()

        for remote in self.git_remote_show():
            # TODO: This shouldn't happen here:
            if remote.strip() == "":
                continue
            remote_dict = remotes.get(remote, {})
            for remote_branch in self.git_get_branches():
                remote_dict[remote_branch] = self.get_handles(remote_branch)
            # TODO: head_branch: git_get_active_branch
            remotes[remote] = remote_dict
        return remotes

    def save_collection(self, collection, branch=None,
                        msg="Collection saved."):
        # TODO: branch is not used yet.

        # TODO: What about remotes?

        if not isinstance(collection, Collection):
            raise TypeError("Can't save non-collection type: %s" %
                            type(collection))

        # handle we no longer have
        no_more = set(self.get_indexed_files()).difference(
            [self._key2filename(k) for k in collection.keys()])
        for gone in no_more:
            # collection meta data is treated differently
            # TODO: Actually collection meta data isn't treated yet at all!
            if gone != 'collection':
                self.git_remove(gone)

        # update everything else to be safe
        for k, v in collection.iteritems():
            with open(opj(self.path, self._key2filename(k)), 'w') as ofile:
                ofile.write('\n'.join(['%s = %s' % (cat, val)
                                      for cat, val in zip(('handle_id',
                                                           'last_seen',
                                                           'metadata'), v)]))
            self.git_add(self._key2filename(k))

        self.git_commit(msg)

    def add_handle(self, handle, name):
        """Adds a handle to the collection

        Parameters:
        -----------
        handle: Handle
          For now, this has to be a locally available handle.
        name: str
          name of the handle. This is required to be unique with respect to the
          collection.
         """
        # TODO: Does a handle have a default name? => repo's name

        # Writing plain text for now. This is supposed to change to use
        # rdflib or sth.
        with open(opj(self.path, name), 'w') as f:
            f.write("handle_id = %s\n" % handle.get_datalad_id())
            f.write("last_seen = %s\n" % handle.path)
            f.write("metadata = %s\n" % handle.get_metadata())
            # what else? maybe default view or sth.

        # TODO: write to collection file:
        # entry for default layout?

        self.git_add(name)
        self.git_commit("Add handle %s." % name)

    def remove_handle(self, key):

        # TODO: also accept a Handle instead of a name
        # TODO: remove stuff from collection file
        self.git_remove(self._key2filename(key))
        self.git_commit("Removed handle %s." % key)


    # TODO: -----------------------------------------------------------
    # def get_handles(self):
    #
    #     return [Handle(x[2]) for x in self.handles]
    #
    # def get_handle(self, name):
    #
    #     return [Handle(x[2]) for x in self.handles if x[0] == name][0]


