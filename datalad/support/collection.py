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
            # For now read a list of handles' names, ids and paths
            # as a proof of concept:

            for filename in self.get_indexed_files():
                if filename != 'collection':
                    with open(filename, 'r') as f:
                        for line in f.readlines():
                            if line.startswith("handle_id = "):
                                id_ = line[12:]
                            elif line.startswith("last_seen = "):
                                url = line[12:]
                            else:
                                continue
                self.handles.append((filename, id_, url))



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

        # TODO: write to collection file:
        # entry for default layout?

        self.git_add(name)
        self.git_commit("Add handle %s." % name)

        # currently need to add to self.handles:
        self.handles.append((name, handle.get_datalad_id(), handle.path))

    def remove_handle(self, name):
        # TODO: remove stuff from collection file
        self.git_remove(name)
        self.git_commit("Removed handle %s." % name)

    def publish(self, target):
        # TODO: lintian check for all handles and may be the collection itself,
        # especially cross-platform checks
        # first (try to) upload handles
        # check all is fine
        # update location for uploaded handles
        # upload collection itself
        pass

    def get_handles(self):
        # return list?
        pass

    def get_handle(self, name):
        pass

    def update_metadata_cache(self, handle):
        pass

# handle files:
#   - some cross-collection ID (annex uuid of origin?)
#   - name within scope of the collection is the file's name
#
#   - location: collection's source of the handle.?
#           -> some valid git url?
#           -> in case of THE local collection it's the local path?
#           => datalad/utils.py:def get_local_file_url(fname):
#   - may be a default view?

#   metadata cache per each handle

# collection file:
#   - default layout (FS)
