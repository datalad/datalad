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
from os.path import join as opj, exists
import logging

from annexrepo import AnnexRepo

lgr = logging.getLogger('datalad.dataset')


class Handle(AnnexRepo):
    """Representation of a dataset handled by datalad.

    Implementations of datalad commands are supposed to use this rather than AnnexRepo or GitRepo directly,
    since any restrictions on annexes required by datalad due to its cross-platform distribution approach are handled
    within this class. Also an AnnexRepo has no idea of any datalad configuration needs, of course.

    """

    def __init__(self, path, url=None, direct=False, runner=None):
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
        direct: bool
          if True, force git-annex to operate in direct mode

        """

        super(Handle, self).__init__(path, url, direct=direct, runner=runner)

        datalad_path = opj(self.path, '.datalad')
        if not exists(datalad_path):
            os.mkdir(datalad_path)
            # create ID file:
            with open(opj(datalad_path, 'handle_id'), 'w') as f:
                f.write(self.repo.config_reader().get_value("annex", "uuid"))
            self.add_to_git(opj('.datalad', 'handle_id'),
                            "Created datalad handle id.")

    def __eq__(self, obj):
        """Decides whether or not two instances of this class are equal.

        This is done by comparing the base repository path.
        """
        return self.path == obj.path

    def get_datalad_id(self):
        """Get the identifier of the handle.

        Returns
        -------
        str
        """

        with open(opj(self.path, '.datalad', 'handle_id'), 'r') as f:
            return f.readline()

    def get(self, files):
        """get the actual content of files

        This command gets the actual content of the files in `list`.
        """
        self.annex_get(files)
        # For now just pass
        # TODO:

    def _commit(self, msg):
        """Commit changes to repository

        Parameters:
        -----------
        msg: str
            commit-message
        """

        if self.is_direct_mode():
            self.annex_proxy('git commit -m "%s"' % msg)
        else:
            self.git_commit(msg)

    def add_to_annex(self, files, commit_msg="Added file(s) to annex."):
        """Add file(s) to the annex.

        Adds files to the annex and commits.

        Parameters
        ----------
        commit_msg: str
            commit message
        files: list
            list of paths to add to the annex; Can also be a str, in case of a single path.
        """

        self.annex_add(files)
        self._commit(commit_msg)

    def add_to_git(self, files, commit_msg="Added file(s) to git."):
        """Add file(s) directly to git

        Adds files directly to git and commits.

        Parameters
        ----------
        commit_msg: str
            commit message
        files: list
            list of paths to add to git; Can also be a str, in case of a single path.
        """
        self.annex_add_to_git(files)
        self._commit(commit_msg)

# TODO: --------------------------------------------------------------------

    def get_metadata(self):
        """whatever this may return at the end
            => rdflib?!
        """
        # check whether .datalad/metadata exists => raise Not Available
        # read it => rdflib
        return "Dummy metadata"
