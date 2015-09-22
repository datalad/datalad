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
from ...support.network import get_url_straight_filename, get_url_deposition_filename

from logging import getLogger
lgr = getLogger('datalad.crawl.annex')

class initiate_handle(object):
    """Action to initiate a handle following one of the known templates
    """
    def __init__(self, template, handle_name, collection_name=None, add_opts=None):
        """
        Parameters
        ----------
        template : str
          Which template (probably matching the collection name) to use
        handle_name : str
          Name of the handle
        collection_name : str, optional
          If None and not present in data, template is taken
        data_fields : list or tuple, optional
          Additional
        :param template:
        :param handle_name:
        :param collection_name:
        :param add_opts:
        :return:
        """
        self.template = template
        self.handle_name =
    def __call__(self, **data):

                        uri="%{url}s",
                        directory="openfmri/%{dataset_dir}s",
                        template="openfmri",
                        # further any additional options
                        dataset="%{dataset}s")

class Annexificator(object):
    """A helper which would encapsulate operation of adding new content to git/annex repo

    If 'filename' field was not found in the data, filename from the url
    gets taken.
    """
    def __init__(self, path, mode=None, options=None, **kwargs):
        """

        Parameters
        ----------
        **kwargs : dict, optional
          to be passed into AnnexRepo
        """


        self.repo = AnnexRepo(path, **kwargs)
        self.mode = mode
        self.options = options or []

    def add(self, filenames):
        raise NotImplementedError()

    def addurl(self, url, filename):
        raise NotImplementedError()
        # TODO: register url within "The DB" after it was added
        self.register_url_in_db(url, filename)

    def register_url_in_db(self, url, filename):
        # might need to go outside -- since has nothing to do with self
        raise NotImplementedError()

    @staticmethod
    def _get_filename_from_url(url):
        filename = get_url_straight_filename(url)
        # if still no filename
        if not filename:
            filename = get_url_deposition_filename(url)
        if not filename:
            raise ValueError("No filename was figured out for %s. "
                             "Please adjust pipeline to provide one" % url)
        return filename

    def __call__(self, **data): # filename=None, get_deposition_filename=False):
        url = data.get('url')

        # figure out the filename. If deposition one was needed, pipeline should
        # have had it explicitly
        filename = data['filename'] if 'filename' in data else self._get_filename_from_url(url)

        lgr.debug("Request to annex %(url)s to %(filename)s", locals())

        # figure out if we need to download it
        #if self.mode in ('relaxed', 'fast'):


        yield data  # There might be more to it!