# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""
This layer makes the difference between an arbitrary annex and a datalad-managed dataset.

"""

import os
from os.path import join, exists

from annexrepo import AnnexRepo

lgr = logging.getLogger('datalad.dataset')

class Dataset(AnnexRepo):
    """Representation of a dataset handled by datalad.

    Implementations of datalad commands are supposed to use this rather than AnnexRepo or GitRepo directly,
    since any restrictions on annexes required by datalad due to its cross-platform distribution approach are handled
    within this class. Also an AnnexRepo has no idea of any datalad configuration needs, of course.

    """

    def __init__(self, path, url=None):
        """Creates a dataset representation from path.

        If `path` is empty, it creates an new repository.
        If `url` is given, it is expected to point to a git repository to create a clone from.

        Parameters
        ----------
        path : str
          path to repository
        url: str
          url to the to-be-cloned repository.
          valid git url according to http://www.kernel.org/pub/software/scm/git/docs/git-clone.html#URLS required.

        """

        super(Dataset, self).__init__(path, url)
        # TODO: what about runner? (dry runs ...)

        # TODO: should work with path (deeper) inside repo! => gitrepo/annexrepo

        dataladPath = join(self.path, '.datalad')
        if not exists(dataladPath):
            os.mkdir(dataladPath)

    def get(self, list):
        """get the actual content of files

        This command gets the actual content of the files in `list`.
        """
        super(Dataset, self).annex_get(list)
        # For now just pass
        # TODO: options
