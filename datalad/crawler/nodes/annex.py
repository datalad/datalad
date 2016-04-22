# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Nodes to interact with annex -- initiate a new handle or operate with existing one

via Annexificator class, which could be used to add files, checkout branches etc
"""

import os
import time
from os.path import expanduser, join as opj, exists, isabs, lexists, curdir, realpath
from os.path import split as ops
from os.path import isdir, islink
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
from ...tests.utils import put_file_under_git

from ...downloaders.providers import Providers
from ...distribution.dataset import Dataset
from ...api import install
from ...support.configparserinc import SafeConfigParserWithIncludes
from ...support.gitrepo import GitRepo, _normalize_path
from ...support.annexrepo import AnnexRepo
from ...support.stats import ActivityStats
from ...support.versions import get_versions
from ...support.network import get_url_straight_filename, get_url_disposition_filename

from ... import cfg
from ...cmd import get_runner

from ..pipeline import CRAWLER_PIPELINE_SECTION
from ..pipeline import initiate_pipeline_config
from ..dbs.files import PhysicalFileStatusesDB, JsonFileStatusesDB
from ..dbs.versions import SingleVersionDB

from logging import getLogger
lgr = getLogger('datalad.crawl.annex')

_runner = get_runner()
_call = _runner.call
_run = _runner.run


# TODO: make use of datalad_stats
@auto_repr
class initiate_handle(object):
    """Action to initiate a handle following one of the known templates
    """
    def __init__(self, template, handle_name=None,  # collection_name=None,
                 path=None, branch=None, backend=None,
                 template_func=None,
                 data_fields=[], add_fields={}, existing=None):
        """
        Parameters
        ----------
        template : str
          Which template (probably matching the collection name) to use.
          TODO: refer to specs of template that it might understand some
          arguments encoded, such as #func=custom_pipeline
        handle_name : str
          Name of the handle. If None, reacts on 'handle_name' in data
        collection_name : str, optional
          If None and not present in data, template is taken
        path : str, optional
          Path were to initiate the handle.  If not specified, would use
          default path for all new handles (DATALAD_CRAWL_COLLECTIONSPATH)
        branch : str, optional
          Which branch to initialize
        backend : str, optional
          Supported by git-annex backend.  By default (if None specified),
          it is MD5E backend to improve compatibility with filesystems
          having a relatively small limit for a maximum path size
        data_fields : list or tuple of str, optional
          Additional fields from data to store into configuration for
          the handle crawling options -- would be passed into the corresponding
          crawler template
        add_fields : dict, optional
          Dictionary of additional fields to store in the crawler configuration
          to be passed into the template
        existing : ('skip', 'raise', 'adjust', 'replace', 'crawl'), optional
          Behavior if encountering existing handle
        """
        # TODO: add_fields might not be flexible enough for storing more elaborate
        # configurations for e.g. "basic" template
        self.template = template
        self.handle_name = handle_name
        ## self.collection_name = collection_name
        self.data_fields = data_fields
        self.add_fields = add_fields
        self.existing = existing
        self.path = path
        self.branch = branch
        # TODO: backend -> backends (https://github.com/datalad/datalad/issues/358)
        self.backend = backend

    def _initiate_handle(self, path, name):
        lgr.info("Initiating handle %s" % name)
        if self.branch is not None:
            # Because all the 'create' magic is stuffed into the constructor ATM
            # we need first initiate a git repository
            git_repo = GitRepo(path, create=True)
            # since we are initiatializing, that branch shouldn't exist yet, thus --orphan
            git_repo.git_checkout(self.branch, options="--orphan")
            # TODO: RF whenevever create becomes a dedicated factory/method
            # and/or branch becomes an option for the "creater"
        backend = self.backend or cfg.get('crawl', 'default backend', default='MD5E')
        repo = AnnexRepo(
             path,
             direct=cfg.getboolean('crawl', 'init direct', default=False),
             #  name=name,
             backend=backend,
             create=True)
        # TODO: centralize
        if backend:
            put_file_under_git(path, '.gitattributes', '* annex.backend=%s' % backend, annexed=False)
        return repo

    def _save_crawl_config(self, handle_path, data):
        kwargs = {f: data[f] for f in self.data_fields}
        # additional options given as a dictionary
        kwargs.update(self.add_fields)
        return initiate_pipeline_config(
            template=self.template,
            path=handle_path,
            kwargs=kwargs,
            commit=True
        )

    def __call__(self, data={}):
        # figure out directory where create such a handle
        handle_name = self.handle_name or data.get('handle_name', None)
        handle_path = opj(os.curdir, handle_name) \
            if self.path is None \
            else self.path

        data_updated = updated(data, {'handle_path': handle_path,
                                      'handle_name': handle_name})
        lgr.debug("Request to initialize a handle %s at %s", handle_name, handle_path)
        init = True
        if exists(handle_path):
            # TODO: config crawl.collection.existing = skip|raise|replace|crawl|adjust
            # TODO: config crawl.collection.crawl_new = false|true
            existing = self.existing or 'skip'
            if existing == 'skip':
                lgr.info("Skipping handle %s since already exists" % handle_name)
                yield data_updated
                return
            elif existing == 'raise':
                raise RuntimeError("%s already exists" % handle_path)
            elif existing == 'replace':
                _call(rmtree, handle_path)
            elif existing == 'adjust':
                # E.g. just regenerate configs/meta
                init = False
            else:  # TODO: 'crawl'  ;)
                raise ValueError(self.existing)
        if init:
            _call(self._initiate_handle, handle_path, handle_name)
        _call(self._save_crawl_config, handle_path, data)

        yield data_updated


class Annexificator(object):
    """A helper which would encapsulate operation of adding new content to git/annex repo

    If 'filename' field was not found in the data, filename from the url
    gets taken.

    'path' field of data (if present) is used to define path within the subdirectory.
    Should be relative. If absolute found -- ValueError is raised
    """
    def __init__(self, path=None, mode='full', options=None,
                 special_remotes=[],
                 allow_dirty=False, yield_non_updated=False,
                 auto_finalize=True,
                 statusdb=None,
                 **kwargs):
        """

        Note that always_commit=False for the used AnnexRepo to minimize number
        of unnecessary commits

        Parameters
        ----------
        mode : str of {'full', 'fast', 'relaxed'}
          What mode of download to use for the content.  In "full" content gets downloaded
          and checksummed (according to the backend), 'fast' and 'relaxed' are just original
          annex modes where no actual download is performed and files' keys are their urls
        special_remotes : list, optional
          List of custom special remotes to initialize and enable by default.
        yield_non_updated : bool, optional
          Either to yield original data (with filepath) if load was not updated in annex
        auto_finalize : bool, optional
          In some cases, if e.g. adding a file in place of an existing directory or placing
          a file under a directory for which there is a file atm, we would 'finalize' before
          carrying out the operation
        statusdb : {'json', 'fileattr'}, optional
          DB of file statuses which will be used to figure out if remote load has changed.
          If None, no statusdb will be used so Annexificator will process every given url
          as if it lead to new content.  'json' -- JsonFileStatusesDB will
          be used which will store information about each provided file/url into a json file.
          'fileattr' -- PhysicalFileStatusesDB will be used to decide based on
          information in annex and file(s) mtime on the disk.
          Note that statusdb "lives" within branch, so switch_branch would drop existing DB (which
          should get committed within the branch) and would create a new one if db is requested
          again.
        **kwargs : dict, optional
          to be passed into AnnexRepo
        """
        if path is None:
            path = realpath(curdir)
        # TODO: commented out to ease developing for now
        #self.repo = _call(AnnexRepo, path, **kwargs)
        # TODO: backend -- should be fetched from the config I guess... or should we
        # give that duty to the handle initialization routine to change default backend?
        # Well -- different annexifiers might have different ideas for the backend, but
        # then those could be overriden via options
        self.repo = AnnexRepo(path, always_commit=False, **kwargs)

        git_remotes = self.repo.git_get_remotes()
        if special_remotes:
            for remote in special_remotes:
                if remote not in git_remotes:
                    self.repo.annex_initremote(
                            remote,
                            ['encryption=none', 'type=external', 'autoenable=true',
                             'externaltype=%s' % remote])

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


    # def add(self, filename, url=None):
    #     # TODO: modes
    #     self.repo.annex_addurl_to_file(filename, url, batch=True #, TODO  backend
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


    def __call__(self, data):  # filename=None, get_disposition_filename=False):
        # Some checks
        assert(self.mode is not None)
        stats = data.get('datalad_stats', ActivityStats())

        url = data.get('url')
        if url:
            stats.urls += 1

        fpath = self._get_fpath(data, stats, url)
        filepath = opj(self.repo.path, fpath)

        lgr.debug("Request to annex %(url)s to %(fpath)s", locals())

        # since filename could have come from url -- let's update with it
        updated_data = updated(data, {'filename': ops(fpath)[1],
                                      #TODO? 'filepath': filepath
                                      })
        remote_status = None
        if self.statusdb is not None and self._statusdb is None:
            if isinstance(self.statusdb, string_types):
                # Initiate the DB
                self._statusdb = {
                    'json': JsonFileStatusesDB,
                    'fileattr': PhysicalFileStatusesDB}[self.statusdb](annex=self.repo)
            else:
                # use provided persistent instance
                self._statusdb = self.statusdb
        statusdb = self._statusdb
        if url:
            downloader = self._providers.get_provider(url).get_downloader(url)

            # request status since we would need it in either mode
            remote_status = data['url_status'] if 'url_status' in data else downloader.get_status(url)
            if lexists(filepath):
                # Check if URL provides us updated content.  If not -- we should do nothing
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
                if self.mode == 'relaxed' or (statusdb is not None and not statusdb.is_different(fpath, remote_status, url)):
                    # TODO:  check if remote_status < local_status, i.e. mtime jumped back
                    # and if so -- warning or may be according to some config setting -- skip
                    # e.g. config.get('crawl', 'new_older_files') == 'skip'
                    lgr.debug("Skipping download. URL %s doesn't provide new content for %s.  New status: %s",
                              url, filepath, remote_status)
                    stats.skipped += 1
                    if self.yield_non_updated:
                        yield updated_data  # There might be more to it!
                    return
        else:
            # just to mark file as still of interest to us so it doesn't get wiped out later
            # as it should have happened if we removed creation/tracking of that file intentionally
            if statusdb:
                statusdb.get(fpath)

        if not url:
            lgr.debug("Adding %s to annex without url being provided" % (filepath))
            # So we have only filename
            assert(fpath)
            # Just add into git directly for now
            # TODO: tune  annex_add so we could use its json output, and may be even batch it
            out_json = _call(self.repo.annex_add, fpath, options=self.options)
        # elif self.mode == 'full':
        #     # Since addurl ignores annex.largefiles we need first to download that file and then
        #     # annex add it
        #     # see http://git-annex.branchable.com/todo/make_addurl_respect_annex.largefiles_option
        #     lgr.debug("Downloading %s into %s and adding to annex" % (url, filepath))
        #     def _download_and_git_annex_add(url, fpath):
        #         # Just to feed into _call for dry-run
        #         filepath_downloaded = downloader.download(url, filepath, overwrite=True, stats=stats)
        #         assert(filepath_downloaded == filepath)
        #         self.repo.annex_add(fpath, options=self.options)
        #         # and if the file ended up under annex, and not directly under git -- addurl
        #         # TODO: better function which explicitly checks if file is under annex or either under git
        #         if self.repo.file_has_content(fpath):
        #             stats.add_annex += 1
        #             self.repo.annex_addurl_to_file(fpath, url, batch=True)
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
                    # If directory - tricky, since we would want then to check if no
                    # staged changes under
                    _call(self._check_no_staged_changes_under_dir, filepath, stats=stats)
                    _call(rmtree, filepath)
                else:
                    _call(unlink, filepath)
                _call(stats.increment, 'overwritten')
            else:
                _call(self._check_non_existing_filepath, filepath, stats=stats)
            # TODO: We need to implement our special remote here since no downloaders used
            if self.mode == 'full' and remote_status and remote_status.size:  # > 1024**2:
                lgr.info("Need to download %s from %s. No progress indication will be reported"
                         % (naturalsize(remote_status.size), url))
            out_json = _call(self.repo.annex_addurl_to_file, fpath, url, options=annex_options, batch=True)
            added_to_annex = 'key' in out_json

            if self.mode == 'full' or not added_to_annex:
                # we need to adjust our download stats since addurl doesn't do that and we do not use our downloaders here
                _call(stats.increment, 'downloaded')
                _call(stats.increment, 'downloaded_size', _call(lambda: os.stat(filepath).st_size))

        # file might have been added but really not changed anything (e.g. the same README was generated)
        # TODO:
        #if out_json:  # if not try -- should be here!
        _call(stats.increment, 'add_annex' if 'key' in out_json else 'add_git')

        # TODO!!:  sanity check that no large files are added to git directly!

        # So we have downloaded the beast
        # Since annex doesn't care to set mtime for the symlink itself we better set it outselves
        if lexists(filepath):  # and islink(filepath):
            if remote_status:
                # Set mtime of the symlink or git-added file itself
                # utime dereferences!
                # _call(os.utime, filepath, (time.time(), remote_status.mtime))
                # *nix only!  TODO
                if remote_status.mtime:
                    _call(lmtime, filepath, remote_status.mtime)
                if statusdb:
                    _call(statusdb.set, filepath, remote_status)
            else:
                # we still need to inform db about this file so later it would signal to remove it
                # if we no longer care about it
                if statusdb:
                    _call(statusdb.set, filepath)

        self._states.add("Updated git/annex from a remote location")

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

        For instance we can't save into a file d/file if d is a file, not
        a directory
        """
        # if file doesn't exist we need to verify that there is no conflicts
        dirpath, name = ops(filepath)
        if dirpath:
            # we need to assure that either that directory exists or directories
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

    def _get_fpath(self, data, stats, url=None):
        """Return relative path (fpath) to the file based on information in data or url
        """
        # figure out the filename. If disposition one was needed, pipeline should
        # have had it explicitly
        fpath = filename = \
            data['filename'] if 'filename' in data else self._get_filename_from_url(url)

        stats.files += 1

        if filename is None:
            stats.skipped += 1
            raise ValueError("No filename were provided or could be deduced from url=%r" % url)
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

    def switch_branch(self, branch, parent=None, must_exist=None):
        """Node generator to switch branch, returns actual node

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
        """
        def switch_branch(data):
            """Switches to the branch %s""" % branch
            # if self.repo.dirty
            list(self.finalize()(data))
            # statusdb is valid only within the same branch
            self._statusdb = None
            existing_branches = self.repo.git_get_branches()
            if must_exist is not None:
                assert must_exist == (branch in existing_branches)
            if branch not in existing_branches:
                # TODO: this should be a part of the gitrepo logic
                if parent is None:
                    # new detached branch
                    lgr.info("Checking out a new detached branch %s" % (branch))
                    self.repo.git_checkout(branch, options="--orphan")
                    if self.repo.dirty:
                        self.repo.git_remove('.', r=True, f=True)  # TODO: might be insufficient if directories etc  TEST/fix
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

    def merge_branch(self, branch, target_branch=None,
                     strategy=None, commit=True, one_commit_at_a_time=False, skip_no_changes=None):
        """Merge a branch into a current branch

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
          Either to commit when merge is complete
        one_commit_at_at_time: bool, optional
          Either to generate
        skip_no_changes: None or bool, optional
          Either to not perform any action if there is no changes from previous merge
          point. If None, config TODO will be consulted with default of being True (i.e. skip
          if no changes)
        """
        # TODO: support merge of multiple branches at once
        assert(strategy in (None, 'theirs'))

        def merge_branch(data):

            if target_branch is not None:
                orig_branch = self.repo.git_get_active_branch()
                target_branch_ = target_branch
                list(self.switch_branch(target_branch_)(data))
            else:
                orig_branch = None
                target_branch_ = self.repo.git_get_active_branch()

            if self.repo.dirty:
                raise RuntimeError("Requested to merge another branch while current state is dirty")

            last_merged_checksum = self.repo.git_get_merge_base([target_branch_, branch])
            if last_merged_checksum == self.repo.git_get_hexsha(branch):
                lgr.debug("Branch %s doesn't provide any new commits for current HEAD" % branch)
                skip_no_changes_ = skip_no_changes
                if skip_no_changes is None:
                    # TODO: skip_no_changes = config.getboolean('crawl', 'skip_merge_if_no_changes', default=True)
                    skip_no_changes_ = True
                if skip_no_changes_:
                    lgr.debug("Skipping the merge")
                    return

            if one_commit_at_a_time:
                all_to_merge = list(
                        self.repo.git_get_branch_commits(
                                branch,
                                limit='left-only',
                                stop=last_merged_checksum,
                                value='hexsha'))[::-1]
            else:
                all_to_merge = [branch]

            nmerges = len(all_to_merge)
            plmerges = "s" if nmerges>1 else ""
            lgr.info("Initiating %(nmerges)d merge%(plmerges)s of %(branch)s using strategy %(strategy)s", locals())
            options = ['--no-commit'] if not commit else []

            for to_merge in all_to_merge:
                # we might have switched away to orig_branch
                if self.repo.git_get_active_branch() != target_branch_:
                    self.repo.git_checkout(target_branch_)
                if strategy is None:
                    self.repo.git_merge(to_merge, options=options)
                elif strategy == 'theirs':
                    self.repo.git_merge(to_merge, options=["-s", "ours", "--no-commit"], expect_stderr=True)
                    self.repo._git_custom_command([], "git read-tree -m -u %s" % to_merge)
                    self.repo.annex_add('.', options=self.options)  # so everything is staged to be committed
                else:
                    raise NotImplementedError(strategy)

                if commit:
                    if strategy is not None:
                        msg = branch if (nmerges == 1) else ("%s (%s)" % (branch, to_merge))
                        self._commit("Merged %s using strategy %s" % (msg, strategy), options=["-a"])
                else:
                    # Record into our activity stats
                    stats = data.get('datalad_stats', None)
                    if stats:
                        stats.merges.append([branch, target_branch_])
                if orig_branch is not None:
                    self.repo.git_checkout(orig_branch)
                yield data
        return merge_branch

    def _precommit(self):
        self.repo.precommit()  # so that all batched annexes stop
        if self._statusdb:
            self._statusdb.save()
        # there is something to commit and backends was set but no .gitattributes yet
        path = self.repo.path
        if self.repo.dirty and not exists(opj(path, '.gitattributes')):
            backends = self.repo.default_backends
            if backends:
                # then record default backend into the .gitattributes
                put_file_under_git(path, '.gitattributes', '* annex.backend=%s' % backends[0],
                                   annexed=False)


    # At least use repo._git_custom_command
    def _commit(self, msg=None, options=[]):
        # We need a custom commit due to "fancy" merges and GitPython
        # not supporting that ATM
        # https://github.com/gitpython-developers/GitPython/issues/361
        # and apparently not actively developed
        if msg is not None:
            options = options + ["-m", msg]
        self._precommit()  # so that all batched annexes stop
        self.repo._git_custom_command([], ["git", "commit"] + options)
        #self.repo.commit(msg)
        #self.repo.repo.git.commit(options)

    def _unstage(self, fpaths):
        # self.repo.cmd_call_wrapper.run(["git", "reset"] + fpaths)
        self.repo._git_custom_command(fpaths, ["git", "reset"])

    def _stage(self, fpaths):
        self.repo.git_add(fpaths)
        # self.repo.cmd_call_wrapper.run(["git", "add"] + fpaths)

    def _get_status(self):
        """Custom check of status to see what files were staged, untracked etc
        until
        https://github.com/gitpython-developers/GitPython/issues/379#issuecomment-180101921
        is resolved
        """
        #out, err = self.repo.cmd_call_wrapper.run(["git", "status", "--porcelain"])
        out, err = self.repo._git_custom_command([], ["git", "status", "--porcelain"])
        assert not err
        staged, notstaged, untracked, deleted = [], [], [], []
        for l in out.split('\n'):
            if not l:
                continue
            act = l[:2]  # first two characters is what is happening to the file
            fname = l[3:]
            try:
                {'??': untracked,
                 'A ': staged,
                 'M ': staged,
                 ' M': notstaged,
                 ' D': deleted,
                 }[act].append(fname)
                # for the purpose of this use we don't even want MM or anything else
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

            # figure out versions for all files (so we could handle conflicts with existing
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

            # Verify that everything is under control!
            assert(not notstaged)  # not handling atm, although should be safe I guess just needs logic to not unstage them
            assert(not untracked)  # not handling atm
            assert(not deleted)  # not handling atm
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
                    raise RuntimeError("previous version %s not found among known to DB: %s" % (prev_version, versions_db.versions.keys()))
                # all new versions must be greater than the previous version
                # since otherwise it would mean that we are complementing previous version and it might be
                # a sign of a problem
                assert(all((LooseVersion(prev_version) < LooseVersion(v)) for v in versions))
                # old implementation when we didn't have entire versions db stored
                #new_versions = OrderedDict(versions.items()[version_keys.index(prev_version) + 1:])
                new_versions = versions
                # if we have "new_versions" smallest one smaller than previous -- we got a problem!
                # TODO: how to handle ==? which could be legit if more stuff was added for the same
                # version?  but then if we already tagged with that -- we would need special handling

            if new_versions:
                smallest_new_version = next(iter(new_versions))
                if prev_version:
                    if LooseVersion(smallest_new_version) <= LooseVersion(prev_version):
                        raise ValueError("Smallest new version %s is <= prev_version %s"
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
                assert(nfpaths >= 0)
                assert(nunstaged >= 0)
                _call(self._stage, vfpaths)

                # RF: with .finalize() to avoid code duplication etc
                # ??? what to do about stats and states?  reset them or somehow tune/figure it out?
                vmsg = "Multi-version commit #%d/%d: %s. Remaining unstaged: %d" % (iversion+1, nnew_versions, version, nunstaged)

                if stats:
                    _call(stats.reset)

                if version:
                    _call(setattr, versions_db, 'version', version)
                _call(self._commit, "%s (%s)%s" % (', '.join(self._states), vmsg, stats_str), options=[])
                # unless we update data, no need to yield multiple times I guess
                # but shouldn't hurt
                yield data
            assert(nunstaged == 0)  # we at the end committed all of them!

        return _commit_versions


    def remove_other_versions(self, name=None, overlay=False):
        """Remove other (non-current) versions of the files

        Pretty much to be used in tandem with commit_versions
        """
        def _remove_other_versions(data):
            if overlay:
                raise NotImplementedError(overlay)
            stats = data.get('datalad_stats', None)
            versions_db = SingleVersionDB(self.repo, name=name)

            current_version = versions_db.version

            if not current_version:
                lgr.info("No version information was found, skipping remove_other_versions")
                yield data
                return

            for version, fpaths in iteritems(versions_db.versions):
                # we do not care about non-versioned or current version
                if version is None or current_version == version:
                    continue   # skip current version
                for fpath, vfpath in iteritems(fpaths):
                    vfpathfull = opj(self.repo.path, vfpath)
                    if lexists(vfpathfull):
                        lgr.log(5, "Removing %s of version %s. Current one %s", vfpathfull, version, current_version)
                        os.unlink(vfpathfull)

            if stats:
                stats.versions.append(current_version)

            yield data
        return _remove_other_versions

    #TODO: @borrow_kwargs from api_add_...
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
                delete=True, key=False, commit=commit, allow_dirty=True,
                annex_options=self.options,
                stats=stats,
                **aac_kwargs
            )
            self._states.add("Added files from extracted archives")
            assert(annex is self.repo)   # must be the same annex, and no new created
            # to propagate statistics from this call into commit msg since we commit=False here
            # we update data with stats which gets a new instance if wasn't present
            yield updated(data, {'datalad_stats': stats})
        return _add_archive_content


    # TODO: either separate out commit or allow to pass a custom commit msg?
    def finalize(self, tag=False, existing_tag=None, cleanup=False):
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
          What to do if tag already exists, if None -- warning is issued. If `+suffix`
          +0, +1, +2 ... are tried until available one is found.
        cleanup: bool, optional
          Either to perform cleanup operations, such as 'git gc' and 'datalad clean'
        """
        def _finalize(data):
            self._precommit()
            stats = data.get('datalad_stats', None)
            if self.repo.dirty:  # or self.tracker.dirty # for dry run
                lgr.info("Repository found dirty -- adding and committing")
                _call(self.repo.annex_add, '.', options=self.options)  # so everything is committed

                stats_str = ('\n\n' + stats.as_str(mode='full')) if stats else ''
                _call(self._commit, "%s%s" % (', '.join(self._states), stats_str), options=["-a"])
                if stats:
                    _call(stats.reset)
            else:
                lgr.info("Found branch non-dirty - nothing is committed")

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
                            lgr.warning("There is already a tag %s in the repository. Delete it first if you want it updated" % tag_)
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
                    self.repo.repo.create_tag(tag_, message="Automatically crawled and tagged by datalad %s.%s" % (__version__, stats_str))

            if cleanup:
                total_stats = stats.get_total()
                if total_stats.add_git or total_stats.add_annex or total_stats.merges:
                    if cfg.getboolean('crawl', 'pipeline.housekeeping', default=True):
                        lgr.info("House keeping: gc, repack and clean")
                        # gc and repack
                        self.repo.gc(allow_background=False)
                        clean(annex=self.repo)
                    else:
                        lgr.info("No git house-keeping performed as instructed by config")
                else:
                    lgr.info("No git house-keeping performed as no notable changes to git")

            self._states = set()
            yield data
        return _finalize

    def remove_obsolete(self):
        """Remove obsolete files which were not referenced in queries to db

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
                    _call(self.repo.git_remove, obsolete)
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
        _call(self.repo.git_remove, filename)
        yield data

    def initiate_handle(self, *args, **kwargs):
        """Thin proxy to initiate_handle node which initiates handle as a subhandle to current annexificator
        """
        def _initiate_handle(data):
            for data_ in initiate_handle(*args, **kwargs)(data):
                # Also "register" as a sub-handle if not yet registered
                ds = Dataset(self.repo.path)
                # TODO:  rename handle_  into dataset_
                if data['handle_name'] not in ds.get_dataset_handles():
                    out = install(
                            dataset=ds,
                            path=data_['handle_path'],
                            source=data_['handle_path'],
                            )
                    # TODO: reconsider adding smth to data_ to be yielded"
                yield data_
        return _initiate_handle
