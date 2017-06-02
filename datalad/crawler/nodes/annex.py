# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Nodes to interact with annex -- initiate a new dataset or operate with existing one

via Annexificator class, which could be used to add files, checkout branches, etc
"""

import os
import re
import time
from os import listdir
from os.path import expanduser, join as opj, exists, isabs, lexists, curdir, realpath
from os.path import split as ops
from os.path import isdir, islink
from os.path import relpath
from os import unlink, makedirs
from collections import OrderedDict
from humanize import naturalsize
from six import iteritems
from six import string_types
from distutils.version import LooseVersion
from functools import partial

from git import Repo

from ...version import __version__
from ...api import add_archive_content
from ...api import clean
from ...consts import CRAWLER_META_DIR, CRAWLER_META_CONFIG_FILENAME
from ...utils import rmtree, updated
from ...utils import lmtime
from ...utils import find_files
from ...utils import auto_repr
from ...utils import getpwd
from ...utils import try_multiple
from ...tests.utils import put_file_under_git

from ...downloaders.providers import Providers
from ...distribution.dataset import Dataset
from ...api import create
from ...support.configparserinc import SafeConfigParserWithIncludes
from ...support.gitrepo import GitRepo, _normalize_path
from ...support.annexrepo import AnnexRepo
from ...support.stats import ActivityStats
from ...support.versions import get_versions
from ...support.exceptions import AnnexBatchCommandError
from ...support.external_versions import external_versions
from ...support.network import get_url_straight_filename, get_url_disposition_filename

from ... import cfg
from ...cmd import get_runner

from ..pipeline import CRAWLER_PIPELINE_SECTION
from ..pipeline import initiate_pipeline_config
from ..dbs.files import PhysicalFileStatusesDB, JsonFileStatusesDB
from ..dbs.versions import SingleVersionDB
from datalad.customremotes.base import init_datalad_remote
from datalad.dochelpers import exc_str

from logging import getLogger

lgr = getLogger('datalad.crawl.annex')

_runner = get_runner()
_call = _runner.call
_run = _runner.run


# TODO: make use of datalad_stats
@auto_repr
class initiate_dataset(object):
    """Action to initiate a dataset following one of the known templates
    """

    def __init__(self, template, dataset_name=None,
                 path=None, branch=None, backend=None,
                 template_func=None, template_kwargs=None,
                 add_to_super='auto',
                 data_fields=[], add_fields={}, existing=None):
        """
        Parameters
        ----------
        template : str
          Which template (probably matching the superdataset name) to use.
          TODO: refer to specs of template that it might understand some
          arguments encoded, such as #func=custom_pipeline
        template_func : str, optional
          Explicitly specify the function name within template module
        template_kwargs: dict, optional
          Keyword arguments to pass into the `template_func`.
        dataset_name : str, optional
          Name of the dataset. If None, reacts on 'dataset_name' in data
        path : str, optional
          Path were to initiate the dataset.  If not specified, would use
          default path for all new datasets (DATALAD_CRAWL_COLLECTIONSPATH)
        branch : str, optional
          Which branch to initialize
        backend : str, optional
          Supported by git-annex backend.  By default (if None specified),
          it is MD5E backend to improve compatibility with filesystems
          having a relatively small limit for a maximum path size
        add_to_super : bool or 'auto', optional
          Add to super-dataset
        data_fields : list or tuple of str, optional
          Additional fields from data to store into configuration for
          the dataset crawling options -- would be passed into the corresponding
          crawler template
        add_fields : dict, optional
          Dictionary of additional fields to store in the crawler configuration
          to be passed into the template
        existing : ('skip', 'raise', 'adjust', 'replace', 'crawl'), optional
          Behavior if encountering existing dataset
        """
        # TODO: add_fields might not be flexible enough for storing more elaborate
        # configurations for e.g. "basic" template

        self.template = template
        self.template_func = template_func
        self.template_kwargs = template_kwargs
        self.dataset_name = dataset_name
        self.data_fields = data_fields
        self.add_fields = add_fields
        self.existing = existing
        self.path = path
        self.branch = branch
        # TODO: backend -> backends (https://github.com/datalad/datalad/issues/358)
        self.backend = backend
        self.add_to_super = add_to_super

    def _initiate_dataset(self, path, name):
        lgr.info("Initiating dataset %s" % name)

        if self.branch is not None:
            raise NotImplementedError("Disabled for now")
            # because all the 'create' magic is stuffed into the constructor ATM
            # we need first to initiate a git repository
            git_repo = GitRepo(path, create=True)
            # since we are initiating, that branch shouldn't exist yet, thus --orphan
            git_repo.checkout(self.branch, options=["--orphan"])
            # TODO: RF whenevever create becomes a dedicated factory/method
            # and/or branch becomes an option for the "creator"

        backend = self.backend or cfg.obtain('datalad.crawl.default_backend', default='MD5E')
        direct = cfg.obtain('datalad.crawl.init_direct', default=False)

        if direct:
            raise NotImplementedError("Disabled for now to init direct mode ones")

        ds = create(
                path=path,
                force=False,
                # no_annex=False,  # TODO: add as an arg
                # Passing save arg based on backend was that we need to save only if
                #  custom backend was specified, but now with dataset id -- should always save
                # save=not bool(backend),
                # annex_version=None,
                annex_backend=backend,
                #git_opts=None,
                #annex_opts=None,
                #annex_init_opts=None
        )
        if self.add_to_super:
            # place hack from 'add-to-super' times here
            sds = ds.get_superdataset()
            if sds is not None:
                lgr.debug("Adding %s as a subdataset to %s", ds, sds)
                sds.add(ds.path, save=False)
                # this leaves the subdataset staged in the parent
            elif str(self.add_to_super) != 'auto':
                raise ValueError(
                    "Was instructed to add to super dataset but no super dataset "
                    "was found for %s" % ds
                )

        # create/AnnexRepo specification of backend does it non-persistently in .git/config
        if backend:
            put_file_under_git(path, '.gitattributes', '* annex.backend=%s' % backend, annexed=False)

        return ds

    def _save_crawl_config(self, dataset_path, data):
        kwargs = self.template_kwargs or {}
        # update with those from data
        kwargs.update({f: data[f] for f in self.data_fields})
        # additional options given as a dictionary
        kwargs.update(self.add_fields)
        return initiate_pipeline_config(
            template=self.template,
            template_func=self.template_func,
            template_kwargs=kwargs,
            path=dataset_path,
            commit=True
        )

    def __call__(self, data={}):
        # figure out directory where create such a dataset
        dataset_name = self.dataset_name or data.get('dataset_name', None)
        dataset_path = opj(os.curdir, dataset_name) \
            if self.path is None \
            else self.path

        data_updated = updated(data, {'dataset_path': dataset_path,
                                      'dataset_name': dataset_name})
        lgr.debug("Request to initialize a dataset %s at %s", dataset_name, dataset_path)
        init = True
        if exists(dataset_path):
            # TODO: config crawl.subdataset.existing = skip|raise|replace|crawl|adjust
            # TODO: config crawl.subdataset.crawl_new = false|true
            existing = self.existing or 'skip'
            if existing == 'skip':
                lgr.info("Skipping dataset %s since already exists" % dataset_name)
                yield data_updated
                return
            elif existing == 'raise':
                raise RuntimeError("%s already exists" % dataset_path)
            elif existing == 'replace':
                _call(rmtree, dataset_path)
            elif existing == 'adjust':
                # E.g. just regenerate configs/meta
                init = False
            else:  # TODO: 'crawl'  ;)
                raise ValueError(self.existing)
        if init:
            _call(self._initiate_dataset, dataset_path, dataset_name)
        _call(self._save_crawl_config, dataset_path, data)

        yield data_updated


class Annexificator(object):
    """A helper which would encapsulate the operation of adding new content to git/annex repo

    If 'filename' field was not found in the data, filename from the URL
    gets taken.

    'path' field of data (if present) is used to define path within the subdirectory.
    Should be relative. If absolute found -- ValueError is raised
    """

    def __init__(self, path=None,
                 no_annex=False,
                 mode='full', options=None,
                 special_remotes=[],
                 allow_dirty=False, yield_non_updated=False,
                 auto_finalize=True,
                 statusdb=None,
                 skip_problematic=False,
                 **kwargs):
        """

        Note that always_commit=False for the used AnnexRepo to minimize number
        of unnecessary commits

        Parameters
        ----------
        mode : str of {'full', 'fast', 'relaxed'}
          What mode of download to use for the content.  In "full" content gets downloaded
          and checksummed (according to the backend), 'fast' and 'relaxed' are just original
          annex modes where no actual download is performed and the files' keys are their URLs
        no_annex : bool
          Assume/create a simple Git repository, without git-annex
        special_remotes : list, optional
          List of custom special remotes to initialize and enable by default
        yield_non_updated : bool, optional
          Either to yield original data (with filepath) if load was not updated in annex
        auto_finalize : bool, optional
          In some cases, if e.g. adding a file in place of an existing directory or placing
          a file under a directory for which there is a file atm, we would 'finalize' before
          carrying out the operation
        statusdb : {'json', 'fileattr'}, optional
          DB of file statuses which will be used to figure out if remote load has changed.
          If None, no statusdb will be used so Annexificator will process every given URL
          as if it leads to new content.  'json' -- JsonFileStatusesDB will
          be used which will store information about each provided file/url into a JSON file.
          'fileattr' -- PhysicalFileStatusesDB will be used to decide based on information in
          annex and file(s) mtime on the disk.
          Note that statusdb "lives" within the branch, so switch_branch would drop existing DB (which
          should get committed within the branch) and would create a new one if DB is requested
          again.
        skip_problematic: bool, optional
          If True, it would not raise an exception if e.g. url is 404 or forbidden -- then just
          nothing is yielded, and effectively that entry is skipped
        **kwargs : dict, optional
          to be passed into AnnexRepo
        """
        if path is None:
            path = realpath(curdir)
        # TODO: commented out to ease developing for now
        # self.repo = _call(AnnexRepo, path, **kwargs)
        # TODO: backend -- should be fetched from the config I guess... or should we
        # give that duty to the dataset initialization routine to change default backend?
        # Well -- different annexifiers might have different ideas for the backend, but
        # then those could be overriden via options

        if exists(path):
            if not exists(opj(path, '.git')):
                if (len(listdir(path))) and (not allow_dirty):
                    raise RuntimeError("Directory %s is not empty." % path)

        self.repo = (GitRepo if no_annex else AnnexRepo)(path, always_commit=False, **kwargs)

        git_remotes = self.repo.get_remotes()
        if special_remotes:
            if no_annex: # isinstance(self.repo, GitRepo):
                raise ValueError("Cannot have special remotes in a simple git repo")

            # TODO: move under AnnexRepo with proper testing etc
            repo_info_repos = [v for k, v in self.repo.repo_info().items()
                               if k.endswith(' repositories')]
            annex_remotes = {r['description']: r for r in sum(repo_info_repos, [])}

            for remote in special_remotes:
                if remote not in git_remotes:
                    if remote in annex_remotes:
                        # Already known - needs only enabling
                        lgr.info("Enabling existing special remote %s" % remote)
                        self.repo.enable_remote(remote)
                    else:
                        init_datalad_remote(self.repo, remote, autoenable=True)

        self.mode = mode
        self.options = options or []
        self.auto_finalize = auto_finalize
        self._states = set()
        # TODO: may be should be a lazy centralized instance?
        self._providers = Providers.from_config_files()
        self.yield_non_updated = yield_non_updated

        if (not allow_dirty) and self.repo.dirty:
            raise RuntimeError("Repository %s is dirty.  Finalize your changes before running this pipeline" % path)

        self.statusdb = statusdb
        self._statusdb = None  # actual DB to be instantiated later
        self.skip_problematic = skip_problematic

    # def add(self, filename, url=None):
    #     # TODO: modes
    #     self.repo.add_url_to_file(filename, url, batch=True #, TODO  backend
    #                                    )
    #     raise NotImplementedError()
    #
    # def addurl(self, url, filename):
    #     raise NotImplementedError()
    #     # TODO: register url within "The DB" after it was added
    #     self.register_url_in_db(url, filename)
    #
    def register_url_in_db(self, url, filename):
        # might need to go outside -- since has nothing to do with self
        raise NotImplementedError()

    def reset(self):
        if self._statusdb:
            self._statusdb.reset()

    @staticmethod
    def _get_filename_from_url(url):
        if url is None:
            return None
        filename = get_url_straight_filename(url)
        # if still no filename
        if not filename:
            filename = get_url_disposition_filename(url)
        if not filename:
            raise ValueError("No filename was figured out for %s. "
                             "Please adjust pipeline to provide one" % url)
        return filename

    def _get_url_status(self, data, url):
        """A helper to return url_status if url_status is present in data
         otherwise request a new one
         """
        if 'url_status' in data:
            return data['url_status']
        else:
            downloader = self._providers.get_provider(url).get_downloader(url)
            return downloader.get_status(url)

    def __call__(self, data):  # filename=None, get_disposition_filename=False):
        # some checks
        assert (self.mode is not None)
        stats = data.get('datalad_stats', ActivityStats())

        url = data.get('url')
        if url:
            stats.urls += 1

        fpath = self._get_fpath(data, stats, return_None=True)
        url_status = None
        if url:
            try:
                url_status = self._get_url_status(data, url)
            except Exception:
                if self.skip_problematic:
                    stats.skipped += 1
                    lgr.debug("Failed to obtain status for url %s" % url)
                    return
                raise
            if fpath is None:
                # pick it from url_status and give for "reprocessing"
                fpath = self._get_fpath(data, stats, filename=url_status.filename)

        if not fpath:
            if self.skip_problematic:
                stats.skipped += 1
                lgr.debug("Failed to figure out filename for url %s" % url)
                return
            raise ValueError("No filename was provided")

        filepath = opj(self.repo.path, fpath)

        lgr.debug("Request to annex %(url)s to %(fpath)s", locals())
        # since filename could have come from url -- let's update with it
        updated_data = updated(data, {'filename': ops(fpath)[1],
                                      # TODO? 'filepath': filepath
                                      })

        if self.statusdb is not None and self._statusdb is None:
            if isinstance(self.statusdb, string_types):
                # initiate the DB
                self._statusdb = {
                    'json': JsonFileStatusesDB,
                    'fileattr': PhysicalFileStatusesDB}[self.statusdb](annex=self.repo)
            else:
                # use provided persistent instance
                self._statusdb = self.statusdb

        statusdb = self._statusdb
        if url:
            if lexists(filepath):
                # check if URL provides us updated content.  If not -- we should do nothing
                # APP1:  in this one it would depend on local_status being asked first BUT
                #        may be for S3 support where statusdb would only record most recent
                #        modification time
                # local_status = self.statusdb.get(fpath)
                # remote_status = downloader.get_status(url, old_status=local_status)
                # if remote_status == local_status:  # WIP TODO not is_status_different(local_status, remote_status):
                # APP2:  no explicit local_status
                # if self.mode != 'full' and fpath == '1-copy.dat':
                #     import pdb; pdb.set_trace()

                # TODO: what if the file came from another url bearing the same mtime and size????
                #       unlikely but possible.  We would need to provide URL for comparison(s)
                if self.mode == 'relaxed' or (
                        statusdb is not None and not statusdb.is_different(fpath, url_status, url)):
                    # TODO:  check if remote_status < local_status, i.e. mtime jumped back
                    # and if so -- warning or may be according to some config setting -- skip
                    # e.g. config.get('crawl', 'new_older_files') == 'skip'
                    lgr.debug("Skipping download. URL %s doesn't provide new content for %s.  New status: %s",
                              url, filepath, url_status)
                    stats.skipped += 1
                    if self.yield_non_updated:
                        yield updated_data  # there might be more to it!
                    return
        else:
            # just to mark file as still of interest to us so it doesn't get wiped out later
            # as it should have happened if we removed creation/tracking of that file intentionally
            if statusdb:
                statusdb.get(fpath)

        if not url:
            lgr.debug("Adding %s to annex without url being provided" % filepath)
            # so we have only filename
            assert fpath
            # just add into git directly for now
            # TODO: tune  add so we could use its json output, and may be even batch it
            out_json = _call(self.repo.add, fpath, options=self.options)
        # elif self.mode == 'full':
        #     # since addurl ignores annex.largefiles we need first to download that file and then
        #     # annex add it
        #     # see http://git-annex.branchable.com/todo/make_addurl_respect_annex.largefiles_option
        #     lgr.debug("Downloading %s into %s and adding to annex", url, filepath)
        #     def _download_and_git_annex_add(url, fpath):
        #         # Just to feed into _call for dry-run
        #         filepath_downloaded = downloader.download(url, filepath, overwrite=True, stats=stats)
        #         assert filepath_downloaded == filepath
        #         self.repo.add(fpath, options=self.options)
        #         # and if the file ended up under annex, and not directly under git -- addurl
        #         # TODO: better function which explicitly checks if file is under annex or either under git
        #         if self.repo.file_has_content(fpath):
        #             stats.add_annex += 1
        #             self.repo.add_url_to_file(fpath, url, batch=True)
        #         else:
        #             stats.add_git += 1
        #     _call(_download_and_git_annex_add, url, fpath)
        else:
            # !!!! If file shouldn't get under annex due to largefile setting -- we must download it!!!
            # TODO: http://git-annex.branchable.com/todo/make_addurl_respect_annex.largefiles_option/#comment-b43ef555564cc78c6dee2092f7eb9bac
            # we should make use of   matchexpression   command, but that might reincarnated
            # above code so just left it commented out for now
            annex_options = self.options
            if self.mode == 'full':
                lgr.debug("Downloading %s into %s and adding to annex" % (url, filepath))
            else:
                annex_options = annex_options + ["--%s" % self.mode]
                lgr.debug("Pointing %s to %s within annex in %s mode" % (url, filepath, self.mode))

            if lexists(filepath):
                lgr.debug("Removing %s since it exists before fetching a new copy" % filepath)
                if isdir(filepath):
                    # if directory - tricky, since we would want then to check if no
                    # staged changes under
                    _call(self._check_no_staged_changes_under_dir, filepath, stats=stats)
                    _call(rmtree, filepath)
                else:
                    _call(unlink, filepath)
                _call(stats.increment, 'overwritten')
            else:
                _call(self._check_non_existing_filepath, filepath, stats=stats)
            # TODO: We need to implement our special remote here since no downloaders used
            if self.mode == 'full' and url_status and url_status.size:  # > 1024**2:
                lgr.info("Need to download %s from %s. No progress indication will be reported"
                         % (naturalsize(url_status.size), url))
            try:
                out_json = try_multiple(
                    6, AnnexBatchCommandError, 3,  # up to 3**5=243 sec sleep
                    _call,
                    self.repo.add_url_to_file, fpath, url,
                    options=annex_options, batch=True)
            except AnnexBatchCommandError as exc:
                if self.skip_problematic:
                    lgr.warning("Skipping %s due to %s", url, exc_str(exc))
                    return
                else:
                    raise
            added_to_annex = 'key' in out_json

            if self.mode == 'full' or not added_to_annex:
                # we need to adjust our download stats since addurl doesn't do that and we do
                # not use our downloaders here
                _call(stats.increment, 'downloaded')
                _call(stats.increment, 'downloaded_size', _call(lambda: os.stat(filepath).st_size))

        # file might have been added but really not changed anything (e.g. the same README was generated)
        # TODO:
        # if out_json:  # if not try -- should be here!
        # File might have been not modified at all, so let's check its status first
        changed = set().union(*self._get_status(args=[fpath]))
        if fpath in changed:
            _call(stats.increment,
                  'add_annex'
                    if ('key' in out_json and out_json['key'] is not None)
                    else 'add_git'
                  )
        else:
            _call(stats.increment, 'skipped')

        # TODO!!:  sanity check that no large files are added to git directly!

        # so we have downloaded the beast
        # since annex doesn't care to set mtime for the symlink itself, we better set it ourselves
        if lexists(filepath):  # and islink(filepath):
            if url_status:
                # set mtime of the symlink or git-added file itself
                # utime dereferences!
                # _call(os.utime, filepath, (time.time(), remote_status.mtime))
                # *nix only!  TODO
                if url_status.mtime:
                    _call(lmtime, filepath, url_status.mtime)
                if statusdb:
                    _call(statusdb.set, filepath, url_status)
            else:
                # we still need to inform DB about this file so later it would signal to remove it
                # if we no longer care about it
                if statusdb:
                    _call(statusdb.set, filepath)

        self._states.add("Updated git/annex from a remote location")

        # WiP: commented out to do testing before merge
        # db_filename = self.db.get_filename(url)
        # if filename is not None and filename != db_filename:
        #     # need to download new
        #     self.repo.add_urls
        #     # remove old
        #     self.repo.remove([db_filename])
        #     self.db.set_filename(url, filename)
        # # figure out if we need to download it
        # #if self.mode in ('relaxed', 'fast'):
        # git annex addurl --pathdepth=-1 --backend=SHA256E '-c' 'annex.alwayscommit=false' URL
        # with subsequent "drop" leaves no record that it ever was here
        yield updated_data  # There might be more to it!

    def _check_no_staged_changes_under_dir(self, dirpath, stats=None):
        """Helper to verify that we can "safely" remove a directory
        """
        dirty_files = self._get_status()
        dirty_files = sum(dirty_files, [])
        dirpath_normalized = _normalize_path(self.repo.path, dirpath)
        for dirty_file in dirty_files:
            if stats:
                _call(stats.increment, 'removed')
            if dirty_file.startswith(dirpath_normalized):
                if self.auto_finalize:
                    self.finalize()({'datalad_stats': stats})
                    return
                else:
                    raise RuntimeError(
                        "We need to save some file instead of directory %(dirpath)s "
                        "but there are uncommitted changes (%(dirty_file)s) under "
                        "that directory.  Please commit them first" % locals())

    def _check_non_existing_filepath(self, filepath, stats=None):
        """Helper to verify that we can safely save into the target path

        For instance, we can't save into a file d/file if d is a file, not
        a directory
        """
        # if file doesn't exist we need to verify that there are no conflicts
        dirpath, name = ops(filepath)
        if dirpath:
            # we need to assure that either the directory exists or directories
            # on the way to it exist and are not a file by some chance
            while dirpath:
                if lexists(dirpath):
                    if not isdir(dirpath):
                        # we have got a problem
                        # HANDLE THE SITUATION
                        # check if given file is not staged for a commit or dirty
                        dirty_files = self._get_status()
                        # it was a tuple of 3
                        dirty_files = sum(dirty_files, [])
                        dirpath_normalized = _normalize_path(self.repo.path, dirpath)
                        if dirpath_normalized in dirty_files:
                            if self.auto_finalize:
                                self.finalize()({'datalad_stats': stats})
                            else:
                                raise RuntimeError(
                                    "We need to annex file %(filepath)s but there is a file "
                                    "%(dirpath)s in its path which destiny wasn't yet decided "
                                    "within git.  Please commit or remove it before trying "
                                    "to annex this new file" % locals())
                        lgr.debug("Removing %s as it is in the path of %s" % (dirpath, filepath))
                        _call(os.unlink, dirpath)
                        if stats:
                            _call(stats.increment, 'overwritten')
                    break  # in any case -- we are done!

                dirpath, _ = ops(dirpath)
                if not dirpath.startswith(self.repo.path):
                    # shouldn't happen!
                    raise RuntimeError("We escaped the border of the repository itself. "
                                       "path: %s  repo: %s" % (dirpath, self.repo.path))

    def _get_fpath(self, data, stats, filename=None, return_None=False):
        """Return relative path (fpath) to the file based on information in data

        Raises
        ------
        ValueError if no filename field was provided
        """
        # figure out the filename. If disposition one was needed, pipeline should
        # have had it explicitly
        if filename is None:
            filename = data['filename'] if 'filename' in data else None
            stats.files += 1
        fpath = filename

        if filename is None:
            if return_None:
                return None
            stats.skipped += 1
            raise ValueError("No filename were provided")
        elif isabs(filename):
            stats.skipped += 1
            raise ValueError("Got absolute filename %r" % filename)

        path_ = data.get('path', None)
        if path_:
            # TODO: test all this handling of provided paths
            if isabs(path_):
                stats.skipped += 1
                raise ValueError("Absolute path %s was provided" % path_)
            fpath = opj(path_, fpath)

        return fpath

    def switch_branch(self, branch, parent=None, must_exist=None, allow_remote=True):
        """Node generator to switch branches, returns actual node

        Parameters
        ----------
        branch : str
          Name of the branch
        parent : str or None, optional
          If parent is provided, it will serve as a parent of the branch. If None,
          detached new branch will be created
        must_exist : bool or None, optional
          If None, doesn't matter.  If True, would fail if branch does not exist.  If
          False, would fail if branch already exists
        allow_remote : bool, optional
          If not exists locally, will try to find one among remote ones
        """

        def switch_branch(data):
            """Switches to the branch %s""" % branch
            # if self.repo.dirty
            list(self.finalize()(data))
            # statusdb is valid only within the same branch
            self._statusdb = None
            existing_branches = self.repo.get_branches()
            if must_exist is not None:
                assert must_exist == (branch in existing_branches)

            # TODO: this should be a part of the gitrepo logic
            if branch not in existing_branches and allow_remote:
                remote_branches = self.repo.get_remote_branches()
                remotes = sorted(set([b.split('/', 1)[0] for b in remote_branches]))
                for r in ['origin'] + remotes:  # ok if origin tested twice
                    remote_branch = "%s/%s" % (r, branch)
                    if remote_branch in remote_branches:
                        lgr.info("Did not find branch %r locally. Checking out remote one %r"
                                 % (branch, remote_branch))
                        self.repo.checkout(remote_branch, options=['--track'])
                        # refresh the list -- same check will come again
                        existing_branches = self.repo.get_branches()
                        break

            if branch not in existing_branches:
                if parent is None:
                    # new detached branch
                    lgr.info("Checking out a new detached branch %s" % (branch))
                    self.repo.checkout(branch, options=["--orphan"])
                    if self.repo.dirty:
                        self.repo.remove('.', r=True, f=True)  # TODO: might be insufficient if directories etc TEST/fix
                else:
                    if parent not in existing_branches:
                        raise RuntimeError("Parent branch %s does not exist" % parent)
                    lgr.info("Checking out %s into a new branch %s" % (parent, branch))
                    self.repo.checkout(parent, options=["-b", branch])
            else:
                lgr.info("Checking out an existing branch %s" % (branch))
                self.repo.checkout(branch)
            yield updated(data, {"git_branch": branch})

        return switch_branch

    def merge_branch(self, branch, target_branch=None,
                     strategy=None, commit=True, one_commit_at_a_time=False,
                     skip_no_changes=None, **merge_kwargs):
        """Merge a branch into the current branch

        Parameters
        ----------
        branch: str
          Branch to be merged
        target_branch: str, optional
          Into which branch to merge. If not None, it will be checked out first.
          At the end we will return into original branch
        strategy: None or 'theirs', optional
          With 'theirs' strategy remote branch content is used 100% as is.
          'theirs' with commit=False can be used to prepare data from that branch for
          processing by further steps in the pipeline
        commit: bool, optional
          Either to commit when merge is complete or not
        one_commit_at_at_time: bool, optional
          Either to generate or not
        skip_no_changes: None or bool, optional
          Either to not perform any action if there are no changes from previous merge
          point. If None, config TODO will be consulted with default of being True (i.e. skip
          if no changes)
        """
        # TODO: support merge of multiple branches at once
        assert (strategy in (None, 'theirs'))

        def merge_branch(data):

            if target_branch is not None:
                orig_branch = self.repo.get_active_branch()
                target_branch_ = target_branch
                list(self.switch_branch(target_branch_)(data))
            else:
                orig_branch = None
                target_branch_ = self.repo.get_active_branch()

            if self.repo.dirty:
                raise RuntimeError("Requested to merge another branch while current state is dirty")

            last_merged_checksum = self.repo.get_merge_base([target_branch_, branch])
            skip_no_changes_ = skip_no_changes
            if skip_no_changes is None:
                # TODO: skip_no_changes = config.getboolean('crawl', 'skip_merge_if_no_changes', default=True)
                skip_no_changes_ = True

            if last_merged_checksum == self.repo.get_hexsha(branch):
                lgr.debug("Branch %s doesn't provide any new commits for current HEAD" % branch)
                if skip_no_changes_:
                    lgr.debug("Skipping the merge")
                    return

            if one_commit_at_a_time:
                all_to_merge = list(
                    self.repo.get_branch_commits(
                        branch,
                        limit='left-only',
                        stop=last_merged_checksum,
                        value='hexsha'))[::-1]
            else:
                all_to_merge = [branch]

            nmerges = len(all_to_merge)

            # There were no merges, but we were instructed to not skip
            if not nmerges and skip_no_changes_ is False:
                # so we will try to merge it nevertheless
                lgr.info("There was nothing to merge but we were instructed to merge due to skip_no_changes=False")
                all_to_merge = [branch]
                nmerges = 1

            plmerges = "s" if nmerges > 1 else ""
            lgr.info("Initiating %(nmerges)d merge%(plmerges)s of %(branch)s using strategy %(strategy)s", locals())
            options = ['--no-commit'] if not commit else []

            for to_merge in all_to_merge:
                # we might have switched away to orig_branch
                if self.repo.get_active_branch() != target_branch_:
                    self.repo.checkout(target_branch_)
                if strategy is None:
                    self.repo.merge(to_merge, options=options, **merge_kwargs)
                elif strategy == 'theirs':
                    self.repo.merge(to_merge, options=["-s", "ours", "--no-commit"],
                                    expect_stderr=True, **merge_kwargs)
                    self.repo._git_custom_command([], "git read-tree -m -u %s" % to_merge)
                    self.repo.add('.', options=self.options)  # so everything is staged to be committed
                else:
                    raise NotImplementedError(strategy)

                if commit:
                    if strategy is not None:
                        msg = branch if (nmerges == 1) else ("%s (%s)" % (branch, to_merge))
                        self._commit("Merged %s using strategy %s" % (msg, strategy), options=["-a"])
                else:
                    # record into our activity stats
                    stats = data.get('datalad_stats', None)
                    if stats:
                        stats.merges.append([branch, target_branch_])
                if orig_branch is not None:
                    self.repo.checkout(orig_branch)
                yield data

        return merge_branch

    def _precommit(self):
        self.repo.precommit()  # so that all batched annexes stop
        if self._statusdb:
            self._statusdb.save()
        # there is something to commit and backends was set but no .gitattributes yet
        path = self.repo.path
        if self.repo.dirty and not exists(opj(path, '.gitattributes')) and isinstance(self.repo, AnnexRepo):
            backends = self.repo.default_backends
            if backends:
                # then record default backend into the .gitattributes
                put_file_under_git(path, '.gitattributes', '* annex.backend=%s' % backends[0],
                                   annexed=False)

    # at least use repo._git_custom_command
    def _commit(self, msg=None, options=[]):
        # we need a custom commit due to "fancy" merges and GitPython
        # not supporting that ATM
        # https://github.com/gitpython-developers/GitPython/issues/361
        # and apparently not actively developed
        msg = str(msg).strip()
        if not msg:
            # we need to provide some commit msg, could may be deduced from current status
            # TODO
            msg = "a commit"
        msg = GitRepo._get_prefixed_commit_msg(msg)
        if msg is not None:
            options = options + ["-m", msg]
        self._precommit()  # so that all batched annexes stop
        self.repo._git_custom_command([], ["git", "commit"] + options)
        # self.repo.commit(msg)
        # self.repo.repo.git.commit(options)

    def _unstage(self, fpaths):
        # self.repo.cmd_call_wrapper.run(["git", "reset"] + fpaths)
        self.repo._git_custom_command(fpaths, ["git", "reset"])

    def _stage(self, fpaths):
        self.repo.add(fpaths, git=True)
        # self.repo.cmd_call_wrapper.run(["git", "add"] + fpaths)

    def _get_status(self, args=[]):
        """Custom check of status to see what files were staged, untracked etc
        until
        https://github.com/gitpython-developers/GitPython/issues/379#issuecomment-180101921
        is resolved
        """
        # out, err = self.repo.cmd_call_wrapper.run(["git", "status", "--porcelain"])
        cmd_args = ["git", "status", "--porcelain"] + args
        staged, notstaged, untracked, deleted = [], [], [], []
        statuses = {
            '??': untracked,
            'A ': staged,
            'M ': staged,
            ' M': notstaged,
            ' D': deleted,  #     rm-ed  smth committed before
            'D ': deleted,  # git rm-ed  smth committed before
            'AD': (staged, deleted)  # so we added, but then removed before committing
                                     # generaly shouldn't happen but in some tricky S3 cases crawling did happen :-/
                                     # TODO: handle "properly" by committing before D happens
        }

        if isinstance(self.repo, AnnexRepo) and self.repo.is_direct_mode():
            statuses['AD'] = staged
            out, err = self.repo.proxy(cmd_args)
        else:
            out, err = self.repo._git_custom_command([], cmd_args)
            assert not err

        for l in out.split('\n'):
            if not l:
                continue
            act = l[:2]  # first two characters is what is happening to the file
            fname = l[3:]
            try:
                act_list = statuses[act]
                if isinstance(act_list, tuple):  # like in case of AD
                    for l in act_list:
                        l.append(fname)
                else:
                    act_list.append(fname)
                # for the purpose of this use, we don't even want MM or anything else
            except KeyError:
                raise RuntimeError("git status %r not yet supported. TODO" % act)
        return staged, notstaged, untracked, deleted

    def commit_versions(self,
                        regex,
                        dirs=True,  # either match directory names
                        rename=False,
                        **kwargs):
        """Generate multiple commits if multiple versions were staged

        Parameters
        ----------
        TODO
        **kwargs: dict, optional
          Passed to get_versions
        """

        def _commit_versions(data):
            self._precommit()  # so that all batched annexes stop

            # figure out versions for all files (so we could dataset conflicts with existing
            # non versioned)
            # TODO:  we need to care only about staged (and unstaged?) files ATM!
            # So let's do it.  And use separate/new Git repo since we are doing manual commits through
            # calls to git.  TODO: RF to avoid this
            # Not usable for us ATM due to
            # https://github.com/gitpython-developers/GitPython/issues/379
            # repo = Repo(self.repo.path)
            #
            # def process_diff(diff):
            #     """returns full paths for files in the diff"""
            #     out = []
            #     for obj in diff:
            #         assert(not obj.renamed)  # not handling atm
            #         assert(not obj.deleted_file)  # not handling atm
            #         assert(obj.a_path == obj.b_path)  # not handling atm
            #         out.append(opj(self.repo.path, obj.a_path))
            #     return out
            #
            # staged = process_diff(repo.index.diff('HEAD'))#repo.head.commit))
            # notstaged = process_diff(repo.index.diff(None))
            staged, notstaged, untracked, deleted = self._get_status()

            # verify that everything is under control!
            assert (not notstaged)  # not handling atm, although should be safe I guess just needs logic
            # to not unstage them
            assert (not untracked)  # not handling atm
            assert (not deleted)  # not handling atm
            if not staged:
                return  # nothing to be done -- so we wash our hands off entirely

            if not dirs:
                raise NotImplementedError("ATM matching will happen to dirnames as well")

            versions = get_versions(staged, regex, **kwargs)

            if not versions:
                # no versioned files were added, nothing to do really
                for d in self.finalize()(data):
                    yield d
                return

            # we don't really care about unversioned ones... overlay and all that ;)
            if None in versions:
                versions.pop(None)

            # take only new versions to deal with
            versions_db = SingleVersionDB(self.repo)
            prev_version = versions_db.version

            if prev_version is None:
                new_versions = versions  # consider all!
            else:
                version_keys = list(versions.keys())
                if prev_version not in versions_db.versions:
                    # shouldn't happen
                    raise RuntimeError(
                        "previous version %s not found among known to DB: %s" % (prev_version, versions_db.versions.keys()))
                # all new versions must be greater than the previous version
                # since otherwise it would mean that we are complementing previous version and it might be
                # a sign of a problem
                # Well -- so far in the single use-case with openfmri it was that they added
                # derivatives for the same version, so I guess we will allow for that, thus allowing =
                assert (all((LooseVersion(prev_version) <= LooseVersion(v)) for v in versions))
                # old implementation when we didn't have entire versions db stored
                # new_versions = OrderedDict(versions.items()[version_keys.index(prev_version) + 1:])
                new_versions = versions
                # if we have "new_versions" smallest one smaller than previous -- we got a problem!
                # TODO: how to dataset ==? which could be legit if more stuff was added for the same
                # version?  but then if we already tagged with that -- we would need special handling

            if new_versions:
                smallest_new_version = next(iter(new_versions))
                if prev_version:
                    if LooseVersion(smallest_new_version) < LooseVersion(prev_version):
                        raise ValueError("Smallest new version %s is < prev_version %s"
                                         % (smallest_new_version, prev_version))

            versions_db.update_versions(versions)  # store all new known versions

            # early return if no special treatment is needed
            nnew_versions = len(new_versions)
            if nnew_versions <= 1:
                # if a single new version -- no special treatment is needed, but we need to
                # inform db about this new version
                if nnew_versions == 1:
                    _call(setattr, versions_db, 'version', smallest_new_version)
                # we can't return a generator here
                for d in self.finalize()(data):
                    yield d
                return

            # unstage all versioned files from the index
            nunstaged = 0
            for version, fpaths in iteritems(versions):
                nfpaths = len(fpaths)
                lgr.debug("Unstaging %d files for version %s", nfpaths, version)
                nunstaged += nfpaths
                _call(self._unstage, list(fpaths.values()))

            stats = data.get('datalad_stats', None)
            stats_str = ('\n\n' + stats.as_str(mode='full')) if stats else ''

            for iversion, (version, fpaths) in enumerate(iteritems(new_versions)):  # for all versions past previous
                # stage/add files of that version to index
                if rename:
                    # we need to rename and create a new vfpaths
                    vfpaths = []
                    for fpath, vfpath in iteritems(fpaths):
                        # ATM we do not allow unversioned -- should have failed earlier, if not HERE!
                        # assert(not lexists(fpath))
                        # nope!  it must be there from previous commit of a versioned file!
                        # so rely on logic before
                        lgr.debug("Renaming %s into %s" % (vfpath, fpath))
                        os.rename(vfpath, fpath)
                        vfpaths.append(fpath)
                else:
                    # so far we didn't bother about status, so just values would be sufficient
                    vfpaths = list(fpaths.values())
                nfpaths = len(vfpaths)
                lgr.debug("Staging %d files for version %s", nfpaths, version)
                nunstaged -= nfpaths
                assert (nfpaths >= 0)
                assert (nunstaged >= 0)
                _call(self._stage, vfpaths)

                # RF: with .finalize() to avoid code duplication etc
                # ??? what to do about stats and states?  reset them or somehow tune/figure it out?
                vmsg = "Multi-version commit #%d/%d: %s. Remaining unstaged: %d" % (
                iversion + 1, nnew_versions, version, nunstaged)

                if stats:
                    _call(stats.reset)

                if version:
                    _call(setattr, versions_db, 'version', version)
                _call(self._commit, "%s (%s)%s" % (', '.join(self._states), vmsg, stats_str), options=[])
                # unless we update data, no need to yield multiple times I guess
                # but shouldn't hurt
                yield data
            assert (nunstaged == 0)  # we at the end committed all of them!

        return _commit_versions

    def remove_other_versions(self, name=None, db=None,
                              overlay=None, remove_unversioned=False,
                              fpath_subs=None,
                              exclude=None):
        """Remove other (non-current) versions of the files

        Pretty much to be used in tandem with commit_versions

        Parameters
        ----------
        name : str, optional
          Name of the SingleVersionDB to consult (e.g., original name of the branch)
        db : SingleVersionDB, optional
          If provided, `name` must be None.
        overlay : int or callable, optional
          Overlay files of the next version to only replace files from the
          previous version.  If specified as `int`, value will determine how
          many leading levels of .-separated (e.g., of major.minor.patch)
          semantic version format will be used to identify "unique"
          non-overlayable version. E.g. overlay=2, would overlay all .patch
          levels, while starting without overlay for any new major.minor version.
          If a callable, it would be used to augment versions before identifying
          non-overlayable version component.  So in other words `overlay=2`
          should be identical to `overlay=lambda v: '.'.join(v.split('.')[:2])`
        fpath_subs : list of (from, to), optional
          Regex substitutions to apply to (versioned but with version part removed)
          filenames before considering.  To be used whenever file names at some point
          were changed
          (e.g., `ds001_R1.0.1.tgz` one lucky day became `ds000001_R1.0.2.zip`)
        remove_unversioned: bool, optional
          If there is a version defined now, remove those files which are unversioned
          i.e. not listed associated with any version
        exclude : basestring, optional
          Regexp to search to exclude files from considering to remove them if
          `remove_unversioned`.  Passed to `find_files`.  E.g. `README.*` which
          could have been generated in `incoming` branch
        """

        if overlay is None:
            overlay_version_func = lambda x: x
        elif isinstance(overlay, int) and not isinstance(overlay, bool):
            overlay_version_func = lambda v: '.'.join(v.split('.')[:overlay])
        elif hasattr(overlay, '__call__'):
            overlay_version_func = overlay
        else:
            raise TypeError("overlay  must be an int or a callable. Got %s"
                            % repr(overlay))

        if db is not None and name is not None:
            raise ValueError(
                "Must have specified either name or version_db, not both"
            )

        def _remove_other_versions(data):
            stats = data.get('datalad_stats', None)
            versions_db = SingleVersionDB(self.repo, name=name) \
                if db is None \
                else db

            current_version = versions_db.version

            if not current_version:
                lgr.info("No version information was found, skipping remove_other_versions")
                yield data
                return

            current_overlay_version = overlay_version_func(current_version)
            prev_version = None
            tracked_files = {}  # track files in case of overlaying
            for version, fpaths in iteritems(versions_db.versions):
                # sanity check since we now will have assumption that versions
                # are sorted
                if prev_version is not None:
                    assert(prev_version < LooseVersion(version))
                prev_version = LooseVersion(version)
                overlay_version = overlay_version_func(version)
                # we do not care about non-versioned or current "overlay" version
                #import pdb; pdb.set_trace()
                if version is None:
                    continue

                files_to_remove = []
                if current_overlay_version == overlay_version and \
                    LooseVersion(version) <= LooseVersion(current_version):
                    # the same overlay but before current version
                    # we need to track the last known within overlay and if
                    # current updates, remove older version
                    fpaths_considered = {}
                    for fpath, vfpath in fpaths.items():
                        if fpath_subs:
                            fpath_orig = fpath
                            for from_, to_ in fpath_subs:
                                fpath = re.sub(from_, to_, fpath)
                            if fpath in fpaths_considered:
                                # May be it is not that severe, but for now we will
                                # crash if there is a collision
                                raise ValueError(
                                    "Multiple files (%s, %s) collided into the same name %s",
                                    fpaths_considered[fpath], fpath_orig, fpath
                                )
                            fpaths_considered[fpath] = fpath_orig
                        if fpath in tracked_files:
                            files_to_remove.append(tracked_files[fpath])
                        tracked_files[fpath] = vfpath  # replace with current one

                    if version == current_version:
                        # just clean out those tracked_files with the most recent versions
                        # and remove nothing
                        tracked_files = {}
                else:
                    files_to_remove = fpaths.values()

                for vfpath in files_to_remove:
                    vfpathfull = opj(self.repo.path, vfpath)
                    if os.path.lexists(vfpathfull):
                        lgr.debug(
                            "Removing %s of version %s (overlay %s). "
                            "Current one %s (overlay %s)",
                            vfpathfull, version, overlay_version,
                            current_version, current_overlay_version
                        )
                        os.unlink(vfpathfull)

            assert not tracked_files, "we must not end up having tracked files"
            if remove_unversioned:
                # it might be that we haven't 'recorded' unversioned ones at all
                # and now got an explicit version, so we would just need to remove them all
                # For that we need to get all files which left, and remove them unless they
                # were a versioned file (considered above) for any version
                all_versioned_files = set()
                for versioned_files_ in versions_db.versions.values():
                    all_versioned_files.update(versioned_files_.values())
                for fpath in find_files(
                        '.*',
                        topdir=self.repo.path,
                        exclude=exclude, exclude_datalad=True, exclude_vcs=True
                    ):
                    fpath = relpath(fpath, self.repo.path)  # ./bla -> bla
                    if fpath in all_versioned_files:
                        lgr.log(
                            5, "Not removing %s file since it was versioned",
                            fpath)
                        continue
                    lgr.log(5, "Removing unversioned %s file", fpath)
                    os.unlink(fpath)
            elif exclude:
                lgr.warning("`exclude=%r` was specified whenever remove_unversioned is False", exclude)

            if stats:
                stats.versions.append(current_version)

            yield data

        return _remove_other_versions

    # TODO: @borrow_kwargs from api_add_...
    def add_archive_content(self, commit=False, **aac_kwargs):
        """

        Parameters
        ----------
        aac_kwargs: dict, optional
           Options to pass into api.add_archive_content
        """

        def _add_archive_content(data):
            # if no stats -- they will be brand new each time :-/
            stats = data.get('datalad_stats', ActivityStats())
            archive = self._get_fpath(data, stats)
            # TODO: may be adjust annex_options
            annex = add_archive_content(
                archive, annex=self.repo,
                key=False, commit=commit, allow_dirty=True,
                annex_options=self.options,
                stats=stats,
                **aac_kwargs
            )
            self._states.add("Added files from extracted archives")
            assert (annex is self.repo)  # must be the same annex, and no new one created
            # to propagate statistics from this call into commit msg since we commit=False here
            # we update data with stats which gets a new instance if wasn't present
            yield updated(data, {'datalad_stats': stats})

        return _add_archive_content

    # TODO: either separate out commit or allow to pass a custom commit msg?
    def finalize(self, tag=False, existing_tag=None, cleanup=False, aggregate=False):
        """Finalize operations -- commit uncommited, prune abandoned? etc

        Parameters
        ----------
        tag: bool or str, optional
          If set, information in datalad_stats and data can be used to tag release if
          versions is non-empty.
          If True, simply the last version to be used.  If str, it is .format'ed
          using datalad_stats, so something like "r{stats.versions[0]}" can be used.
          Also `last_version` is provided as the last one from stats.versions (None
          if empty)
        existing_tag: None or '+suffix', optional
          What to do if tag already exists, if None, warning is issued. If `+suffix`,
          +0, +1, +2 ... are tried until available one is found.
        cleanup: bool, optional
          Either to perform cleanup operations, such as 'git gc' and 'datalad clean'
        aggregate: bool, optional
          Aggregate meta-data (ATM no recursion, guessing the type)
        """

        def _finalize(data):
            self._precommit()
            stats = data.get('datalad_stats', None)
            if self.repo.dirty:  # or self.tracker.dirty # for dry run
                lgr.info("Repository found dirty -- adding and committing")
                _call(self.repo.add, '.', options=self.options)  # so everything is committed

                stats_str = ('\n\n' + stats.as_str(mode='full')) if stats else ''
                _call(self._commit, "%s%s" % (', '.join(self._states), stats_str), options=["-a"])
                if stats:
                    _call(stats.reset)
            else:
                lgr.info("Found branch non-dirty -- nothing was committed")

            if aggregate:
                from datalad.api import aggregate_metadata
                aggregate_metadata(dataset=self.repo.path, guess_native_type=True)

            if tag and stats:
                # versions survive only in total_stats
                total_stats = stats.get_total()
                if total_stats.versions:
                    last_version = total_stats.versions[-1]
                    if isinstance(tag, string_types):
                        tag_ = tag.format(stats=total_stats, data=data, last_version=last_version)
                    else:
                        tag_ = last_version
                    # TODO: config.tag.sign
                    stats_str = "\n\n" + total_stats.as_str(mode='full')
                    tags = self.repo.repo.tags
                    if tag_ in tags:
                        # TODO: config.tag.allow_override
                        if existing_tag == '+suffix':
                            lgr.warning(
                                "There is already a tag %s in the repository. Delete it first if you want it updated" % tag_)
                            tag_ = None
                        elif existing_tag is None:
                            suf = 1
                            while True:
                                tag__ = '%s+%d' % (tag_, suf)
                                if tag__ not in tags:
                                    break
                                suf += 1
                            lgr.warning("There is already a tag %s in the repository. Tagging as %s" % (tag_, tag__))
                            tag_ = tag__
                        else:
                            raise ValueError(existing_tag)
                    self.repo.repo.create_tag(tag_, message="Automatically crawled and tagged by datalad %s.%s" % (
                        __version__, stats_str))

            if cleanup:
                total_stats = stats.get_total()
                if total_stats.add_git or total_stats.add_annex or total_stats.merges:
                    if cfg.obtain('datalad.crawl.pipeline.housekeeping', default=True):
                        lgr.info("House keeping: gc, repack and clean")
                        # gc and repack
                        self.repo.gc(allow_background=False)
                        clean(dataset=self.repo.path)
                    else:
                        lgr.info("No git house-keeping performed as instructed by config")
                else:
                    lgr.info("No git house-keeping performed as no notable changes to git")

            self._states = set()
            yield data

        return _finalize

    def remove_obsolete(self):
        """Remove obsolete files which were not referenced in queries to DB

        Note that it doesn't reset any state within statusdb upon call, so shouldn't be
        called multiple times for the same state.
        """

        # made as a class so could be reset
        class _remove_obsolete(object):
            def __call__(self_, data):
                statusdb = self._statusdb
                obsolete = statusdb.get_obsolete()
                if obsolete:
                    files_str = ": " + ', '.join(obsolete) if len(obsolete) < 10 else ""
                    lgr.info('Removing %d obsolete files%s' % (len(obsolete), files_str))
                    stats = data.get('datalad_stats', None)
                    _call(self.repo.remove, obsolete)
                    if stats:
                        _call(stats.increment, 'removed', len(obsolete))
                    for filepath in obsolete:
                        statusdb.remove(filepath)
                yield data

            def reset(self_):
                if self._statusdb:
                    self._statusdb.reset()

        return _remove_obsolete()

    def remove(self, data):
        """Removed passed along file name from git/annex"""
        stats = data.get('datalad_stats', None)
        self._states.add("Removed files")
        filename = self._get_fpath(data, stats)
        # TODO: not sure if we should may be check if exists, and skip/just complain if not
        if stats:
            _call(stats.increment, 'removed')
        if lexists(opj(self.repo.path, filename)):
            _call(self.repo.remove, filename)
        else:
            lgr.warning("Was asked to remove non-existing path %s", filename)
        yield data

    def drop(self, all=False, force=False):
        """Drop crawled file or all files if all is specified"""
        def _drop(data):
            if not all:
                raise NotImplementedError("provide handling to drop specific file")
            else:
                lgr.debug("Dropping all files in %s", self.repo)
                self.repo.drop([], options=['--all'] + ['--force'] if force else [])
        return _drop

    def initiate_dataset(self, *args, **kwargs):
        """Thin proxy to initiate_dataset node which initiates dataset as a subdataset to current annexificator
        """
        # now we can just refer to initiate_dataset which uses create
        return initiate_dataset(*args, **kwargs)
