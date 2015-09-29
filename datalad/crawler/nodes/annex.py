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
from os.path import expanduser, join as opj, exists

from ...utils import rmtree, updated

from ...support.configparserinc import SafeConfigParserWithIncludes
from ...support.annexrepo import AnnexRepo
from ...support.handlerepo import HandleRepo
from ...support.network import get_url_straight_filename, get_url_deposition_filename

from ... import cfg
from ...cmd import get_runner

from ..pipeline import crawler_pipeline_section

from logging import getLogger
lgr = getLogger('datalad.crawl.annex')

_runner = get_runner()
_call = _runner.call
_run = _runner.run


class initiate_handle(object):
    """Action to initiate a handle following one of the known templates
    """
    def __init__(self, template, handle_name=None, collection_name=None,
                 path=None,
                 data_fields=[], add_fields={}, existing='raise'):
        """
        Parameters
        ----------
        template : str
          Which template (probably matching the collection name) to use
        handle_name : str
          Name of the handle. If None, reacts on 'handle_name' in data
        collection_name : str, optional
          If None and not present in data, template is taken
        path : str, optional
          Path were to initiate the handle.  If not specified, would use
          default path for all new handles (DATALAD_CRAWL_COLLECTIONSPATH)
        data_fields : list or tuple of str, optional
          Additional fields from data to store into configuration for
          the handle crawling options -- would be passed into the corresponding
          crawler template
        add_fields : dict, optional
          Dictionary of additional fields to store in the crawler configuration
          to be passed into the template
        existing : ('skip', 'raise', 'replace'), optional
          Behavior if encountering existing handle
        """
        # TODO: add_fields might not be flexible enough for storing more elaborate
        # configurations for e.g. "basic" template
        self.template = template
        self.handle_name = handle_name
        self.collection_name = collection_name
        self.data_fields = data_fields
        self.add_fields = add_fields
        self.existing = existing
        self.path = path

    def _initiate_handle(self, path, name):
        return HandleRepo(
                       path,
                       direct=cfg.getboolean('crawl', 'init direct', default=False),
                       name=name,
                       create=True)

    def _save_crawl_config(self, handle_path, name, data):
        crawl_config = opj(handle_path, '.datalad', 'crawl.cfg')
        cfg = SafeConfigParserWithIncludes()
        cfg.add_section(crawler_pipeline_section)
        def secset(k, v):
            cfg.set(crawler_pipeline_section, k, str(v))
        secset('template', self.template)
        secset('collection', self.collection_name)
        secset('name', name)
        # additional options to be obtained from the data
        for f in self.data_fields:
            secset(f, data[f])
        # additional options given as a dictionary
        for k, v in self.add_fields:
            secset(k, v)
        with open(crawl_config, 'w') as f:
            cfg.write(f)

    def __call__(self, data={}):
        # figure out directory where create such a handle
        handle_name = self.handle_name or data['handle_name']
        if self.path is None:
            crawl_toppath = cfg.get('crawl', 'collectionspath',
                                    default=opj(expanduser('~'), 'datalad', 'crawl'))
            handle_path = opj(crawl_toppath,
                              self.collection_name or self.template,
                              handle_name)
        else:
            handle_path = self.path

        lgr.debug("Request to initialize a handle at %s", handle_path)

        if exists(handle_path):
            if self.existing == 'skip':
                yield data
            elif self.existing == 'raise':
                raise RuntimeError("%s already exists" % handle_path)
            elif self.existing == 'replace':
                _call(rmtree, handle_path)
            else:
                raise ValueError(self.existing)
        _call(self._initiate_handle, handle_path, handle_name)
        _call(self._save_crawl_config, handle_path, handle_name, data)

        yield updated(data, {'handle_path': handle_path,
                             'handle_name': handle_name})
"""

                        uri="%{url}s",
                        directory="openfmri/%{dataset_dir}s",
                        template="openfmri",
                        # further any additional options
                        dataset="%{dataset}s")
"""

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
        # TODO: commented out to ease developing for now
        #self.repo = _call(AnnexRepo, path, **kwargs)
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

    def __call__(self, data):  # filename=None, get_deposition_filename=False):
        url = data.get('url')

        # figure out the filename. If deposition one was needed, pipeline should
        # have had it explicitly
        filename = data['filename'] if 'filename' in data else self._get_filename_from_url(url)

        lgr.debug("Request to annex %(url)s to %(filename)s", locals())
        # Filename still can be None

        # WiP: commented out to do testing before merge
        # db_filename = self.db.get_filename(url)
        # if filename is not None and filename != db_filename:
        #     # need to download new
        #     self.repo.annex_addurls
        #     # remove old
        #     self.repo.git_remove([db_filename])
        #     self.db.set_filename(url, filename)
        # # figure out if we need to download it
        # #if self.mode in ('relaxed', 'fast'):


        yield data  # There might be more to it!