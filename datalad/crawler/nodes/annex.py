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
from os import unlink, makedirs

from ...consts import CRAWLER_META_DIR
from ...utils import rmtree, updated

from ...downloaders.providers import Providers
from ...support.configparserinc import SafeConfigParserWithIncludes
from ...support.gitrepo import GitRepo
from ...support.annexrepo import AnnexRepo
from ...support.handlerepo import HandleRepo
from ...support.network import get_url_straight_filename, get_url_disposition_filename

from ... import cfg
from ...cmd import get_runner

from ..pipeline import CRAWLER_PIPELINE_SECTION

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
        repo = GitRepo(handle_path)
        crawl_config_dir = opj(handle_path, CRAWLER_META_DIR)
        if not exists(crawl_config_dir):
            lgr.log(1, "Creating %s", crawl_config_dir)
            makedirs(crawl_config_dir)

        crawl_config = opj(crawl_config_dir, 'crawl.cfg')
        cfg = SafeConfigParserWithIncludes()
        cfg.add_section(CRAWLER_PIPELINE_SECTION)
        def secset(k, v):
            cfg.set(CRAWLER_PIPELINE_SECTION, k, str(v))
        secset('template', self.template)
        # TODO: why should we set all this information into a handle?
        # handle should be independent of a collection, and if necessary
        # we should be able to track it back to collection(s) of which
        # it belongs to
        #if self.collection_name:
        #    secset('collection', self.collection_name)
        #secset('name', name)
        # additional options to be obtained from the data
        for f in self.data_fields:
            secset(f, data[f])
        # additional options given as a dictionary
        for k, v in self.add_fields:
            secset(k, v)
        with open(crawl_config, 'w') as f:
            cfg.write(f)
        repo.git_add(crawl_config)
        repo.git_commit("Initialized crawling configuration to use template %s" % self.template)


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


class Annexificator(object):
    """A helper which would encapsulate operation of adding new content to git/annex repo

    If 'filename' field was not found in the data, filename from the url
    gets taken.
    """
    def __init__(self, path=None, mode='full', options=None,
                 allow_dirty=False, **kwargs):
        """

        Note that always_commit=False for the used AnnexRepo to minimize number
        of unnecessary commits

        Parameters
        ----------
        mode : str of {'full', 'fast', 'relaxed'}
          What mode of download to use for the content.  In "full" content gets downloaded
          and checksummed (according to the backend), 'fast' and 'relaxed' are just original
          annex modes where no actual download is performed and files' keys are their urls
        **kwargs : dict, optional
          to be passed into AnnexRepo
        """
        if path is None:
            from os.path import curdir
            path = curdir
        # TODO: commented out to ease developing for now
        #self.repo = _call(AnnexRepo, path, **kwargs)
        # TODO: backend -- should be fetched from the config I guess... or should we
        # give that duty to the handle initialization routine to change default backend?
        # Well -- different annexifiers might have different ideas for the backend, but
        # then those could be overriden via options
        self.repo = AnnexRepo(path, always_commit=False, **kwargs)
        self.mode = mode
        self.options = options or []
        self._states = []
        # TODO: may be should be a lazy centralized instance?
        self._providers = Providers.from_config_files()

        if (not allow_dirty) and self.repo.dirty:
            raise RuntimeError("Repository %s is dirty.  Finalize your changes before running this pipeline" % path)

    def add(self, filename, url=None):
        # TODO: modes
        self.repo.annex_addurl_to_file(filename, url#, TODO  backend
                                       )
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
            filename = get_url_disposition_filename(url)
        if not filename:
            raise ValueError("No filename was figured out for %s. "
                             "Please adjust pipeline to provide one" % url)
        return filename

    def __call__(self, data):  # filename=None, get_disposition_filename=False):
        url = data.get('url')


        # figure out the filename. If disposition one was needed, pipeline should
        # have had it explicitly
        filename = data['filename'] if 'filename' in data else self._get_filename_from_url(url)

        # TODO:  some kind of 'path' should be in play here as well
        fpath = filename

        lgr.debug("Request to annex %(url)s to %(fpath)s", locals())
        # Filename still can be None

        # Since addurl ignores annex.largefiles we need first to download that file and then
        # annex add it
        filepath = opj(self.repo.path, fpath)
        if url and exists(filepath):
            lgr.debug("Removing %s since it exists before fetching a new copy" % filepath)
            unlink(filepath)

        assert(self.mode is not None)
        if not url:
            lgr.debug("Adding %s directly into git since no url was provided" % (filepath))
            # So we have only filename
            assert(filename)
            # Thus add directly into git
            _call(self.repo.git_add, filename)
        elif self.mode == 'full':
            lgr.debug("Downloading %s into %s and adding to annex" % (url, filepath))
            # XXX temporarily??? until
            # http://git-annex.branchable.com/todo/make_addurl_respect_annex.largefiles_option
            def _download_and_git_annex_add(url, fpath):
                # Just to feed into _call for dry-run
                filepath_downloaded = self._providers.download(url, filepath)
                assert(filepath_downloaded == filepath)
                self.repo.annex_add(fpath, options=self.options)
                # and if the file ended up under annex, and not directly under git -- addurl
                # TODO:  better function which explicitly checks if file is under annex or either under git
                if self.repo.file_has_content(fpath):
                    self.repo.annex_addurl_to_file(fpath, url)
            _call(_download_and_git_annex_add, url, fpath)
        else:
            annex_options = self.options + ["--%s" % self.mode]
            lgr.debug("Downloading %s into %s and adding to annex in %s mode" % (url, filepath, self.mode))
            _call(self.repo.annex_addurl_to_file, fpath, url, options=annex_options)

        state = "adding files to git/annex"
        if state not in self._states:
            self._states.append(state)

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
        # git annex addurl --pathdepth=-1 --backend=SHA256E '-c' 'annex.alwayscommit=false' URL
        # with subsequent "drop" leaves no record that it ever was here

        yield updated(data, {'filename': filename})  # There might be more to it!

    def switch_branch(self, branch, parent=None):
        """Node generator to switch branch, returns actual node

        Parameters
        ----------
        branch : str
          Name of the branch
        parent : str or None, optional
          If parent is provided, it will serve as a parent of the branch. If None,
          detached new branch will be created
        """
        def switch_branch(data):
            """Switches to the branch %s""" % branch
            # if self.repo.dirty
            list(self.finalize(data))
            existing_branches = self.repo.git_get_branches()
            if branch not in existing_branches:
                # TODO: this should be a part of the gitrepo logic
                if parent is None:
                    # new detached branch
                    lgr.info("Checking out a new detached branch %s" % (branch))
                    self.repo.git_checkout(branch, options="--orphan")
                    self.repo.git_remove('.', r=True, f=True) # TODO: might be insufficient if directories etc  TEST/fix
                else:
                    if parent not in existing_branches:
                        raise RuntimeError("Parent branch %s does not exist" % parent)
                    lgr.info("Checking out %s into a new branch %s" % (parent, branch))
                    self.repo.git_checkout(parent, options="-b %s" % branch)
            else:
                lgr.info("Checking out an existing branch %s" % (branch))
                self.repo.git_checkout(branch)
            yield updated(data, {"git_branch": branch})
        return switch_branch

    def merge_branch(self, branch, strategy=None, commit=True):
        # TODO: support merge of multiple branches at once
        assert(strategy in (None, 'theirs'))
        def merge_branch(data):
            lgr.info("Initiating merge of %(branch)s using strategy %(strategy)s", locals())
            options = '--no-commit' if not commit else ''
            if not commit:
                self._states += ["merge of %s" % branch]
            if strategy is None:
                self.repo.git_merge(branch, options=options)
            elif strategy == 'theirs':
                self.repo.git_merge(branch, options="-s ours --no-commit", expect_stderr=True)
                self.repo.cmd_call_wrapper.run("git read-tree -m -u %s" % branch)
                self.repo.annex_add('.', options=self.options)  # so everything is staged to be committed
                if commit:
                    self._commit("Merged %s using strategy %s" % (branch, strategy), options="-a")
            yield data
        return merge_branch

    def _commit(self, msg=None, options=''):
        # We need a custom commit due to "fancy" merges and GitPython
        # not supporting that ATM
        # https://github.com/gitpython-developers/GitPython/issues/361
        if msg is not None:
            options += " -m %r" % msg
        self.repo.cmd_call_wrapper.run("git commit %s" % options)

    # TODO: either separate out commit or allow to pass a custom commit msg?
    def finalize(self, data):
        """Finalize operations -- commit uncommited, prune abandoned? etc"""

        if self.repo.dirty:  # or self.tracker.dirty # for dry run
            lgr.info("Repository found dirty -- adding and committing")
            #    # TODO: introduce activities tracker
            _call(self.repo.annex_add, '.', options=self.options) # so everything is committed
            _call(self._commit, "Finalizing %s" % ','.join(self._states), options="-a") # TODO: use activities tracker
        else:
            lgr.info("Found branch non-dirty - doing nothing")
        self._states = []
        yield data
