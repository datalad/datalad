# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Nodes to interact with annex -- add files etc
"""

from ...support.annexrepo import AnnexRepo

class Annexificator(object):
    """A helper which would encapsulate operation of adding new content to git/annex repo

    """
    def __init__(self, path, mode=None, options=None):
        self.repo = AnnexRepo(path, create=False)
        self.mode = mode
        self.options = options or []

    def add(self, filenames):
        raise NotImplementedError()

    def addurl(self, url, filename=None):
        raise NotImplementedError()
        # TODO: register url within "The DB" after it was added
        self.register_url_in_db(url, filename)

    def register_url_in_db(self, url, filename):
        # might need to go outside -- since has nothing to do with self
        raise NotImplementedError()

    def __call__(self, **data): # filename=None, content_filename_request=False):
        """Return the "Action" callable which would do all the annexification

        Parameters
        ----------
        filename : str or None, optional
          Filename to be used
        content_filename_request : bool, optional
          Either to request the filename from the website to serve as a value
          for the filename
        """

        pass