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
from os.path import join as opj
import logging

from .gitrepo import GitRepo
from .handle import Handle

lgr = logging.getLogger('datalad.collection')

class Collection(GitRepo):
    """Representation of a datalad collection.
    """

    # __slots__ = []
    # check how slots work with derived classes

    def __init__(self, path, url=None, runner=None):
        """

        Parameters:
        -----------
        path: str
          path to git repository. In case it's not an absolute path, it's
          relative to os.getcwd()

        url: str
          url to the to-be-cloned repository. Requires valid git url according to
          http://www.kernel.org/pub/software/scm/git/docs/git-clone.html#URLS .
        """

        super(Collection, self).__init__(path, url, runner=runner)

        # if not new (how to check for?):
        # read collection file and handles?
        # or do it on demand?

        #

        # is it really a gitrepo or should this one may be a remote of local collection, too?


        # How about THE local collection? On datalad command level or does it
        # have its own class?


    # TODO: add_remote in GitRepo (for local collection)/remove remote
    # TODO: get_metadata or sth. in Handle => modify, commit, republish?


    # Attention: files are valid only if in git.
    # Being present is not sufficient!

    def add_handle(self, handle, name):
        # TODO: Does a handle have a default name?
        with open(opj(self.path, name), 'w') as f:
            #write whatever
            pass
        self.git_add(name)
        self.git_commit("Add handle.")

    def remove_handle(self, name):
        # TODO: git rm
        # os.unlink(opj(self.path, name))
        # self.git_commit("Removed handle.")
        pass

    def publish(self, target):
        # TODO: lintian check for all handles and may be the collection itself,
        # especially cross-platform checks
        pass

    def get_handles(self):
        # return list?
        pass


# handle files:
#   - some cross-collection ID
#   - name within scope of the collection is the file's name
#
#   - location: collection's source of the handle.?
#           -> some valid git url?
#           -> in case of THE local collection it's the local path?
#           => datalad/utils.py:def get_local_file_url(fname):
#   - may be a default view?

# collection file:
#   - default layout (FS)