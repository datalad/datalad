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

import os
import time
from os.path import expanduser, join as opj, exists, isabs, lexists, islink, realpath
from os.path import split as ops
from os import unlink, makedirs
from collections import OrderedDict
from humanize import naturalsize
from six import iteritems

from git import Repo

from ...api import add_archive_content
from ...consts import CRAWLER_META_DIR, CRAWLER_META_CONFIG_FILENAME
from ...utils import rmtree, updated
from ...utils import lmtime
from ...utils import find_files

from ...downloaders.providers import Providers
from ...support.configparserinc import SafeConfigParserWithIncludes
from ...support.gitrepo import GitRepo
from ...support.annexrepo import AnnexRepo
from ...support.handlerepo import HandleRepo
from ...support.stats import ActivityStats
from ...support.versions import get_versions
from ...support.network import get_url_straight_filename, get_url_disposition_filename

from ... import cfg
from ...cmd import get_runner

from ..pipeline import CRAWLER_PIPELINE_SECTION
from ..dbs.files import AnnexFileAttributesDB

from logging import getLogger
lgr = getLogger('datalad.crawl.annex')

_runner = get_runner()
_call = _runner.call
_run = _runner.run

# TODO: make use of datalad_stats
class initiate_handle(object):
    """Action to initiate a handle following one of the known templates
    """
    def __init__(self, template, handle_name=None, collection_name=None,
                 path=None, branch=None,
                 data_fields=[], add_fields={}, existing=None):
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
        branch : str, optional
          Which branch to initialize
        data_fields : list or tuple of str, optional
          Additional fields from data to store into configuration for
          the handle crawling options -- would be passed into the corresponding
          crawler template
        add_fields : dict, optional
          Dictionary of additional fields to store in the crawler configuration
          to be passed into the template
        existing : ('skip', 'raise', 'replace', crawl'), optional
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
        self.branch = branch

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
        return HandleRepo(
                       path,
                       direct=cfg.getboolean('crawl', 'init direct', default=False),
                       name=name,
                       create=True)

    def _save_crawl_config(self, handle_path, name, data):
        lgr.info("Creating handle configuration for %s" % name)
        repo = GitRepo(handle_path)
        crawl_config_dir = opj(handle_path, CRAWLER_META_DIR)
        if not exists(crawl_config_dir):
            lgr.log(1, "Creating %s", crawl_config_dir)
            makedirs(crawl_config_dir)

        crawl_config = opj(crawl_config_dir, CRAWLER_META_CONFIG_FILENAME)
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
        if repo.dirty:
            repo.git_commit("Initialized crawling configuration to use template %s" % self.template)
        else:
            lgr.debug("Repository is not dirty -- not committing")


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

        init = True
        if exists(handle_path):
            # TODO: config crawl.collection.existing = skip|raise|replace|crawl|adjust
            # TODO: config crawl.collection.crawl_new = false|true
            existing = self.existing or 'skip'
            if existing == 'skip':
                lgr.info("Skipping handle %s since already exists" % handle_name)
                yield data
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
        _call(self._save_crawl_config, handle_path, handle_name, data)


        yield updated(data, {'handle_path': handle_path,
                             'handle_name': handle_name})


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
        statusdb : , optional
          DB of file statuses which will be used to figure out if remote load has changed.
          If None, instance of AnnexFileAttributesDB will be used which will decide based on
          information in annex and file(s) mtime on the disk
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
        self._states = []
        # TODO: may be should be a lazy centralized instance?
        self._providers = Providers.from_config_files()
        self.yield_non_updated = yield_non_updated

        if (not allow_dirty) and self.repo.dirty:
            raise RuntimeError("Repository %s is dirty.  Finalize your changes before running this pipeline" % path)

        if statusdb is None:
            statusdb = AnnexFileAttributesDB(annex=self.repo)
        self.statusdb = statusdb


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
        if url:
            downloader = self._providers.get_provider(url).get_downloader(url)

            # request status since we would need it in either mode
            remote_status = downloader.get_status(url)
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
                if self.mode == 'relaxed' or not self.statusdb.is_different(fpath, remote_status, url):
                    # TODO:  check if remote_status < local_status, i.e. mtime jumped back
                    # and if so -- warning or may be according to some config setting -- skip
                    # e.g. config.get('crawl', 'new_older_files') == 'skip'
                    lgr.debug("Skipping download. URL %s doesn't provide new content for %s.  New status: %s",
                              url, filepath, remote_status)
                    stats.skipped += 1
                    if self.yield_non_updated:
                        yield updated_data  # There might be more to it!
                    return

        if not url:
            lgr.debug("Adding %s to annex without url being provided" % (filepath))
            # So we have only filename
            assert(fpath)
            # Just add into git directly for now
            # TODO: tune  annex_add so we could use its json output, and may be even batch it
            out_json = _call(self.repo.annex_add, fpath, options=self.options)
            _call(stats.increment, 'add_annex' if 'key' in out_json else 'add_git')
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
                _call(unlink, filepath)
                _call(stats.increment, 'overwritten')

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

            if out_json:  # if not try -- should be here!
                _call(stats.increment, 'add_annex' if added_to_annex else 'add_git')

        # TODO!!:  sanity check that no large files are added to git directly!

        # So we have downloaded the beast
        # Since annex doesn't care to set mtime for the symlink itself we better set it outselves
        if remote_status and lexists(filepath):  # and islink(filepath):
            # Set mtime of the symlink or git-added file itself
            # utime dereferences!
            # _call(os.utime, filepath, (time.time(), remote_status.mtime))
            # *nix only!  TODO
            _call(lmtime, filepath, remote_status.mtime)

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
        yield updated_data  # There might be more to it!

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

    def merge_branch(self, branch, strategy=None, commit=True, skip_no_changes=None):
        """Merge a branch into a current branch

        Parameters
        ----------
        branch: str
          Branch to be merged
        strategy: None or 'theirs', 'theirs-adhoc', optional
          With 'theirs' strategy remote branch content is used 100% as is.
          'theirs' with commit=False can be used to prepare data from that branch for
          processing by further steps in the pipeline
        commit: bool, optional
          Either to commit when merge is complete
        skip_no_changes: None or bool, optional
          Either to not perform any action if there is no changes from previous merge
          point. If None, config TODO will be consulted with default of being True (i.e. skip
          if no changes)
        """
        # TODO: support merge of multiple branches at once
        assert(strategy in (None, 'theirs'))

        def merge_branch(data):
            if self.repo.dirty:
                raise RuntimeError("Requested to merge another branch while current state is dirty")
            last_merged_checksum = self.repo.git_get_merge_base([self.repo.git_get_active_branch(), branch])
            if last_merged_checksum == self.repo.git_get_hexsha(branch):
                lgr.debug("Branch %s doesn't provide any new commits for current HEAD" % branch)
                skip_no_changes_ = skip_no_changes
                if skip_no_changes is None:
                    # TODO: skip_no_changes = config.getboolean('crawl', 'skip_merge_if_no_changes', default=True)
                    skip_no_changes_ = True
                if skip_no_changes_:
                    lgr.debug("Skipping the merge")
                    return

            lgr.info("Initiating merge of %(branch)s using strategy %(strategy)s", locals())
            options = ['--no-commit'] if not commit else []
            if strategy is None:
                self.repo.git_merge(branch, options=options)
            elif strategy == 'theirs':
                self.repo.git_merge(branch, options=["-s", "ours", "--no-commit"], expect_stderr=True)
                self.repo.cmd_call_wrapper.run("git read-tree -m -u %s" % branch)
                self.repo.annex_add('.', options=self.options)  # so everything is staged to be committed
                if commit:
                    self._commit("Merged %s using strategy %s" % (branch, strategy), options=["-a"])
                else:
                    # Record into our activity stats
                    stats = data.get('datalad_stats', None)
                    if stats:
                        stats.merges.append([branch, self.repo.git_get_active_branch()])
            elif strategy == "theirs-adhoc":
                # since git can't repeat the same merge, we need to do it manually
                """
# method 1 -- via temp commit
git merge -s ours --no-commit --no-ff b2
...
git commit -m 'removed 1234'
# inline git rev-parse 'HEAD^{tree}'
echo 'doing merge from 731cb77efff5a92b1c8ec1b5af4717442f7d9a45' | git commit-tree `git rev-parse 'HEAD^{tree}'` \
 -p HEAD^ -p b2
git reset --hard d5686b10a91d745043c2074d61764a19e8a67bc6 # to that treeish returned

# method 2 --
git merge -s ours --no-commit --no-ff b2
# needs to write .git/MERGE_HEAD  to be used later on for b2
...
git reset --hard $(echo "doing merge via write-tree" | git commit-tree `git write-tree` -p HEAD -p b2)
                """
                raise NotImplementedError()
            yield data
        return merge_branch

    def _commit(self, msg=None, options=[]):
        # We need a custom commit due to "fancy" merges and GitPython
        # not supporting that ATM
        # https://github.com/gitpython-developers/GitPython/issues/361
        if msg is not None:
            options = options + ["-m", msg]
        self.repo.precommit()  # so that all batched annexes stop
        self.repo.cmd_call_wrapper.run(["git", "commit"] + options)

    def _unstage(self, fpaths):
        self.repo.cmd_call_wrapper.run(["git", "reset"] + fpaths)

    def _stage(self, fpaths):
        self.repo.cmd_call_wrapper.run(["git", "add"] + fpaths)


    def commit_versions(self,
                        regex,
                        topdir=curdir,
                        dirs=True,  # either match directory names
                        rename=False,
                        **kwargs):
        """Generate multiple commits if multiple versions were staged
        """
        def _commit_versions(data):
            # figure out versions for all files (so we could handle conflicts with existing
            # non versioned)
            # TODO:  we need to care only about staged (and unstaged?) files ATM!
            # So let's do it.  And use separate/new Git repo since we are doing manual commits through
            # calls to git.  TODO: RF to avoid this
            repo = Repo(self.repo.path)
            staged = repo.

            notstaged = []
            for obj in repo.index.diff(None):
                assert()
                nonstaged

            versions = get_versions(find_files(self.repo.path, dirs=dirs, topdir=topdir), regex, **kwargs)

            # we don't really care about unversioned ones... overlay and all that ;)
            if None in versions:
                versions.pop(None)

            # take only new versions to deal with
            prev_version = None  # TODO

            if prev_version is None:
                new_versions = versions  # consider all!
            else:
                if prev_version not in versions:
                    # probably it should be all ok, we just need to figure out where to start
                    # but for now -- FAIL... TODO
                    raise RuntimeError("previous version %s not found among %s" % (prev_version, versions.keys()))
                version_keys = list(versions.keys())
                new_versions = OrderedDict(versions.items()[version_keys.index(prev_version) + 1:])

            # early return if no special treatment is needed
            nnew_versions = len(new_versions)
            if nnew_versions <= 1:
                # if a single new version -- no special treatment is needed
                # we can't return a generator here
                for d in self.finalize(data):
                    yield d
                return

            # unstage all versioned files from the index
            self.repo.precommit()  # so that all batched annexes stop
            nunstaged = 0  # ???
            for version, fpaths in iteritems(versions):
                nfpaths = len(fpaths)
                lgr.debug("Unstaging %d files for version %s", nfpaths, version)
                nunstaged += nfpaths
                _call(self._unstage, list(fpaths))

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
                # RF: with .finalize to avoid code duplication etc
                # ??? what to do about stats and states?  reset them or somehow tune/figure it out?
                vmsg = "Version #%d/%d: %s. Remaining unstaged: %d " % (iversion, nnew_versions, version, nunstaged)
                _call(self._commit, "%sFinalizing %s %s" % (vmsg, ','.join(self._states), stats_str), options=[])

                # unless we update data, no need to yield multiple times I guess
                # but shouldn't hurt
                yield data
            assert(nunstaged == 0)  # we at the end committed all of them!

        return _commit_versions


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
            assert(annex is self.repo)   # must be the same annex, and no new created
            # to propagate statistics from this call into commit msg since we commit=False here
            # we update data with stats which gets a new instance if wasn't present
            yield updated(data, {'datalad_stats': stats})
        return _add_archive_content

    # TODO: either separate out commit or allow to pass a custom commit msg?
    def finalize(self, data):
        """Finalize operations -- commit uncommited, prune abandoned? etc"""
        self.repo.precommit()
        if self.repo.dirty:  # or self.tracker.dirty # for dry run
            lgr.info("Repository found dirty -- adding and committing")
            #    # TODO: introduce activities tracker
            _call(self.repo.annex_add, '.', options=self.options)  # so everything is committed
            stats = data.get('datalad_stats', None)
            stats_str = stats.as_str(mode='line') if stats else ''
            _call(self._commit, "Finalizing %s %s" % (','.join(self._states), stats_str), options=["-a"])
            if stats:
                _call(stats.reset)
        else:
            lgr.info("Found branch non-dirty - nothing is committed")
        self._states = []
        yield data
