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

import os
from os.path import join as opj, exists
import logging

from .gitrepo import GitRepo
from .handle import Handle
from .exceptions import CollectionBrokenError

lgr = logging.getLogger('datalad.collection')


class Collection(GitRepo):
    """Representation of a datalad collection.
    """

    __slots__ = ['handles']
    # TODO: check how slots work with derived classes

    def __init__(self, path, url=None, runner=None):
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

        Raises:
        -------
        CollectionBrokenError
        """

        super(Collection, self).__init__(path, url, runner=runner)

        self.handles = []

        if not self.get_indexed_files():
            # it's a brand new collection repo.

            # create collection file
            # How to name that file? For now just 'collection'
            #  generally contains:
            #   - default layout on filesystem
            #     (Q: implicitly requires a list of handles?
            #      This would give an additional consistency check)
            pass

        elif 'collection' not in self.get_indexed_files():
            raise CollectionBrokenError("Missing file: 'collection'.")

        else:
            # may be read the collection file/handle infos
            # or may be do it on demand?
            # For now read a list of handles' names, ids, paths and metadata
            # as a proof of concept:

            for filename in self.get_indexed_files():
                if filename != 'collection':
                    with open(filename, 'r') as f:
                        for line in f.readlines():
                            if line.startswith("handle_id = "):
                                id_ = line[12:]
                            elif line.startswith("last_seen = "):
                                url = line[12:]
                            elif line.startswith("metadata = "):
                                md = line[11:]
                            else:
                                continue
                    # TODO: check all is present
                self.handles.append((filename, id_, url, md))

    # Attention: files are valid only if in git.
    # Being present is not sufficient!

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
        # TODO: Does a handle have a default name?

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

        # currently need to add to self.handles:
        self.handles.append((name, handle.get_datalad_id(), handle.path,
                             handle.get_metadata()))

    def remove_handle(self, name):

        # TODO: also accept a Handle instead of a name
        # TODO: remove stuff from collection file
        self.git_remove(name)
        self.git_commit("Removed handle %s." % name)

        for x in self.handles:
            if x[0] == name:
                self.handles.remove(x)

    def publish(self, target):
        # Q: Is this even a class method or just a datalad command?

        # TODO: lintian check for all handles and may be the collection itself,

        # TODO: Figure out uploading procedure
        #   => target should be some Uploader-Interface and (may be) an url, ...

        # especially cross-platform checks
        # first (try to) upload handles
        # check all is fine
        # update location for uploaded handles
        # upload collection itself
        pass

    def get_handles(self):

        return [Handle(x[2]) for x in self.handles]

    def get_handle(self, name):

        return [Handle(x[2]) for x in self.handles if x[0] == name][0]

    def update_metadata_cache(self, handle):

        if isinstance(handle, Handle):
            for h_ in self.handles:
                if h_[1] == handle.get_datalad_id():
                    h_[3] = handle.get_metadata()
        elif isinstance(handle, basestring):
            for h_ in self.handles:
                if h_[2] == handle:
                    h_[3] = Handle(h_[2]).get_metadata()
        else:
            raise TypeError("argument 'handle' is expected either to be "
                            "a 'Handle' or a 'basestring'")