# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""High-level interface for dataset (component) installation

"""

__docformat__ = 'restructuredtext'

import logging
import os
from os.path import join as opj, abspath, relpath, pardir, isabs, isdir, \
    exists, islink, sep, realpath

from six.moves.urllib.parse import quote as urlquote

from datalad.cmd import CommandError
from datalad.cmd import Runner
from datalad.distribution.dataset import Dataset, datasetmethod, \
    resolve_path, EnsureDataset
from datalad.interface.base import Interface
from datalad.support.annexrepo import AnnexRepo, FileInGitError, \
    FileNotInAnnexError
from datalad.support.constraints import EnsureStr, EnsureNone, EnsureChoice, \
    EnsureBool
from datalad.support.exceptions import InsufficientArgumentsError
from datalad.support.gitrepo import GitRepo, GitCommandError
from datalad.support.param import Parameter
from datalad.utils import expandpath, knows_annex, assure_dir, \
    is_explicit_path, on_windows, swallow_logs
from datalad.support.network import RI, URL
from datalad.support.network import DataLadRI
from datalad.support.network import is_url, is_datalad_compat_ri
from datalad.utils import rmtree

lgr = logging.getLogger('datalad.distribution.install')


def _get_git_url_from_source(source):
    """Return URL for cloning associated with a source specification

    For now just resolves DataLadRIs
    """
    # TODO: Probably RF this into RI.as_git_url(), that would be overridden
    # by subclasses or sth. like that

    if source is None:  # TODO: why does this even happen?
        lgr.warning("received 'None' as 'source'.")
        return source

    if not isinstance(source, RI):
        source_ri = RI(source)
    else:
        source_ri = source
    if isinstance(source_ri, DataLadRI):
        # we have got our DataLadRI as the source, so expand it
        source = source_ri.as_git_url()
    else:
        source = str(source_ri)
    return source


def _get_installationpath_from_url(url):
    """Returns a relative path derived from the trailing end of a URL

    This can be used to determine an installation path of a Dataset
    from a URL, analog to what `git clone` does.
    """
    path = url.rstrip('/')
    if '/' in path:
        path = path.split('/')
        if path[-1] == '.git':
            path = path[-2]
        else:
            path = path[-1]
    if path.endswith('.git'):
        path = path[:-4]
    return path


def get_git_dir(path):
    """figure out a repo's gitdir

    '.git' might be a  directory, a symlink or a file

    Parameter
    ---------
    path: str
      currently expected to be the repos base dir

    Returns
    -------
    str
      relative path to the repo's git dir; So, default would be ".git"
    """

    from os.path import isfile
    from os import readlink

    dot_git = opj(path, ".git")
    if not exists(dot_git):
        raise RuntimeError("Missing .git in %s." % path)
    elif islink(dot_git):
        git_dir = readlink(dot_git)
    elif isdir(dot_git):
        git_dir = ".git"
    elif isfile(dot_git):
        with open(dot_git) as f:
            git_dir = f.readline()
            if git_dir.startswith("gitdir:"):
                git_dir = git_dir[7:]
            git_dir = git_dir.strip()

    return git_dir


def _install_subds_from_flexible_source(ds, sm_path, sm_url, recursive):
    """Tries to obtain a given subdataset from several meaningful locations"""
    # shortcut
    vcs = ds.repo
    repo = vcs.repo
    # compose a list of candidate clone URLs
    clone_urls = []
    # if we have a remote, let's check the location of that remote
    # for the presence of the desired submodule
    tracking_branch = repo.active_branch.tracking_branch()
    remote_url = ''
    # remember suffix
    url_suffix = ''
    if tracking_branch:
        # name of the default remote for the active branch
        remote_name = repo.active_branch.tracking_branch().remote_name
        remote_url = vcs.get_remote_url(remote_name, push=False)
        if remote_url.rstrip('/').endswith('/.git'):
            url_suffix = '/.git'
            remote_url = remote_url[:-5]
        # attempt: submodule checkout at parent remote URL
        # We might need to quote sm_path portion, e.g. for spaces etc
        if remote_url and isinstance(RI(remote_url), URL):
            sm_path_url = urlquote(sm_path)
        else:
            sm_path_url = sm_path
        clone_urls.append('{0}/{1}{2}'.format(
            remote_url, sm_path_url, url_suffix))
    # attempt: configured submodule URL
    # TODO: consider supporting DataLadRI here?  or would confuse
    #  git and we wouldn't want that (i.e. not allow pure git clone
    #  --recursive)
    if sm_url.startswith('/') or is_url(sm_url):
        # this seems to be an absolute location -> take as is
        clone_urls.append(sm_url)
    else:
        # need to resolve relative URL
        if not remote_url:
            # we have no remote URL, hence we need to go with the
            # local path
            remote_url = ds.path
        remote_url_l = remote_url.split('/')
        sm_url_l = sm_url.split('/')
        for i, c in enumerate(sm_url_l):
            if c == pardir:
                remote_url_l = remote_url_l[:-1]
            else:
                clone_urls.append('{0}/{1}{2}'.format(
                    '/'.join(remote_url_l),
                    '/'.join(sm_url_l[i:]),
                    url_suffix))
                break
    # now loop over all candidates and try to clone
    subds = Dataset(opj(ds.path, sm_path))
    for clone_url in clone_urls:
        lgr.debug("Attempt clone of subdataset from: {0}".format(clone_url))
        try:
            subds = Install.__call__(
                dataset=subds, path=None, source=clone_url,
                recursive=recursive, add_data_to_git=False)
        except GitCommandError:
            # TODO: failed clone might leave something behind that causes the
            # next attempt to fail as well. Implement safe way to remove clone
            # attempt left-overs.
            continue
        lgr.debug("Update cloned subdataset {0} in parent".format(subds))
        if sm_path in ds.get_subdatasets(absolute=False, recursive=False):
            ds.repo.update_submodule(sm_path, init=True)
        else:
            # submodule is brand-new and previously unknown
            ds.repo.add_submodule(sm_path, url=clone_url)
        _fixup_submodule_dotgit_setup(ds, sm_path)
        return subds


def _install_subds_inplace(ds, path, relativepath, name=None):
    """Register an existing repository in the repo tree as a submodule"""
    # FLOW GUIDE EXIT POINT
    # this is an existing repo and must be in-place turned into
    # a submodule of this dataset
    ds.repo.add_submodule(relativepath, url=None, name=name)
    _fixup_submodule_dotgit_setup(ds, relativepath)
    # return newly added submodule as a dataset
    return Dataset(path)


def _fixup_submodule_dotgit_setup(ds, relativepath):
    """Implementation of our current of .git in a subdataset

    Each subdataset/module has its own .git directory where a standalone
    repository would have it. No gitdir files, no symlinks.
    """
    # move .git to superrepo's .git/modules, remove .git, create
    # .git-file
    path = opj(ds.path, relativepath)
    src_dotgit = get_git_dir(path)

    # at this point install always yields the desired result
    # just make sure
    assert(src_dotgit == '.git')


# TODO: check whether the following is done already:
# install of existing submodule; recursive call; source should not be None!

class Install(Interface):
    """Install a dataset component or entire dataset(s).

    This command can make arbitrary content available in a dataset. This
    includes the fulfillment of existing :term:`subdataset` or file handles in
    a dataset, as well as the addition of subdatasets and such handles for
    content available locally or subdataset remotely.
    """

    _params_ = dict(
        dataset=Parameter(
            args=("-d", "--dataset"),
            doc="""specify the dataset to perform the install operation on.  If
            no dataset is given, an attempt is made to identify the dataset
            based on the current working directory and/or the `path` given""",
            constraints=EnsureDataset() | EnsureNone()),
        path=Parameter(
            args=("path",),
            doc="""path/name of the installation target.  If no `source` is
            provided, and no `dataset` is given or detected, this is
            interpreted as the source URL of a dataset and a destination
            path will be derived from the URL similar to 'git clone'""",
            nargs="*",
            constraints=EnsureStr() | EnsureNone()),
        source=Parameter(
            args=("-s", "--source",),
            doc="url or local path of the installation source",
            constraints=EnsureStr() | EnsureNone()),
        # TODO this probably needs --with-data and --recursive as a plain boolean
        recursive=Parameter(
            args=("-r", "--recursive"),
            constraints=EnsureChoice('datasets', 'data') | EnsureBool(),
            doc="""if set, all content is installed recursively, including
            content of any subdatasets"""),
        add_data_to_git=Parameter(
            args=("--add-data-to-git",),
            action='store_true',
            doc="""flag whether to add data directly to Git, instead of
            tracking data identity only.  Usually this is not desired,
            as it inflates dataset sizes and impacts flexibility of data
            transport"""))

    @staticmethod
    @datasetmethod(name='install')
    def __call__(path=None, source=None, dataset=None,
                 recursive=False, add_data_to_git=False):
        lgr.debug(
		    "Installation attempt started. path=%r, source=%r, dataset=%r, recursive=%r, add_data_to_git=%r",
			path, source, dataset, recursive, add_data_to_git
		)
        # shortcut
        ds = dataset

        if ds is not None and not isinstance(ds, Dataset):
            ds = Dataset(ds)

        if isinstance(path, list):
            if not len(path):
                # normalize value to expected state when nothing was provided
                path = None
            elif len(path) == 1:
                # we can simply continue with the function as called with a
                # single argument
                path = path[0]
            else:
                lgr.debug("Installation of multiple targets was requested: {0}".format(path))
                return [Install.__call__(
                        dataset=ds,
                        path=p,
                        source=source,
                        recursive=recursive) for p in path]

        # resolve the target location (if local) against the provided dataset
        if path is not None:
            # Should work out just fine for regular paths, so no additional
            # conditioning is necessary
            path_ri = RI(path)
            try:
                # Wouldn't work for SSHRI ATM, see TODO within SSHRI
                path = resolve_path(path_ri.localpath, ds)
            except ValueError:
                # URL doesn't point to a local something
                pass

        # any `path` argument that point to something local now resolved and
        # is no longer a URL

        # if we have no dataset given, figure out which one we need to operate
        # on, based on the resolved target location (that is now guaranteed to
        # be specified, but only if path isn't a URL (anymore) -> special case,
        # handles below
        if ds is None and path is not None and not is_datalad_compat_ri(path):
            # try to find a dataset at or above the installation target
            dspath = GitRepo.get_toppath(abspath(path))
            if dspath is None:
                # no top-level dataset found, use path as such
                dspath = path
            ds = Dataset(dspath)

        if ds is None and source is None and path is not None:
            # no dataset, no source
            # this could be a shortcut install call, where the first
            # arg identifies the source
            if is_datalad_compat_ri(path) or os.path.exists(path):
                # we have an actual URL -> this should be the source
                # OR
                # it is not a URL, but it exists locally
                lgr.debug(
                    "Single argument given to install and no dataset found. "
                    "Assuming the argument identifies a source location.")
                source = path
                path = None

        lgr.debug("Resolved installation target: {0}".format(path))

        # Possibly do conversion from source into a git-friendly url
        source_url = _get_git_url_from_source(source)

        if ds is None and path is None and source_url is not None:
            # we got nothing but a source. do something similar to git clone
            # and derive the path from the source_url and continue
            lgr.debug(
                "Neither dataset not target installation path provided. "
                "Assuming installation of a remote dataset. "
                "Deriving destination path from given source {0}".format(
                    source_url))
            ds = Dataset(_get_installationpath_from_url(source_url))

        if not path and ds is None:
            # no dataset, no target location, nothing to do
            raise InsufficientArgumentsError(
                "insufficient information for installation (needs at "
                "least a dataset or an installation path")

        assert(ds is not None)

        lgr.info("Installing {0}{1}".format(
            path if path else ds,
            " from %s" % source_url if source_url else ""
        ))

        vcs = ds.repo
        if vcs is None:
            # TODO check that a "ds.path" actually points to a TOPDIR
            # should be the case already, but maybe nevertheless check
            existed = ds.path and exists(ds.path)

            # We possibly need to consider /.git URL
            candidate_source_urls = [source_url]
            if source_url and not source_url.rstrip('/').endswith('/.git'):
                candidate_source_urls.append('{0}/.git'.format(source_url.rstrip('/')))

            for source_url_ in candidate_source_urls:
                try:
                    lgr.debug("Retrieving a dataset from URL: {0}".format(source_url_))
                    with swallow_logs():
                        vcs = Install._get_new_vcs(ds, source_url_)
                    break  # do not bother with other sources if succeeded
                except GitCommandError:
                    lgr.debug("Failed to retrieve from URL: {0}".format(source_url_))
                    if not existed and ds.path and exists(ds.path):
                        lgr.debug("Wiping out unsuccessful clone attempt at {}".format(ds.path))
                        rmtree(ds.path)
                    if source_url_ == candidate_source_urls[-1]:
                        # Re-raise if failed even with the last candidate
                        lgr.debug("Unable to establish repository instance at {0} from {1}"
                                  "".format(ds.path, candidate_source_urls))
                        raise

        assert(ds.repo)  # is automagically re-evaluated in the .repo property

        runner = Runner()

        if path is None or path == ds.path:
            # if the goal was to install this dataset, we are done,
            # except for 'recursive'.

            # TODO: For now 'recursive' means just submodules.
            # See --with-data vs. -- recursive and figure it out
            if recursive:
                if recursive == "data" and isinstance(ds.repo, AnnexRepo):
                    ds.repo.get('.')
                for sm in ds.repo.get_submodules():
                    _install_subds_from_flexible_source(
                        ds, sm.path, sm.url, recursive=recursive)
            return ds

        # at this point this dataset is "installed", now we can test whether to
        # install something into the dataset

        # needed by the logic below
        assert(isabs(path))

        # express the destination path relative to the root of this dataset
        relativepath = relpath(path, start=ds.path)
        if path.startswith(pardir):
            raise ValueError("installation path outside dataset")

        lgr.debug(
            "Resolved installation target relative to dataset {0}: {1}".format(
                ds, relativepath))

        # this dataset must already know everything necessary
        ###################################################
        # FLOW GUIDE
        #
        # at this point we know nothing about the
        # installation targether
        ###################################################
        try:
            # it is simplest to let annex tell us what we are dealing with
            lgr.debug("Trying to fetch file %s using annex", relativepath)
            if not isinstance(vcs, AnnexRepo):
                assert(isinstance(vcs, GitRepo))
                # FLOW GUIDE
                # this is not an annex repo, but we raise exceptions
                # to be able to treat them alike in the special case handling
                # below
                if not exists(path):
                    raise IOError("path doesn't exist yet, might need special handling")
                elif relativepath in vcs.get_indexed_files():
                    # relativepath is in git
                    raise FileInGitError("We need to handle it as known to git")
                else:
                    raise FileNotInAnnexError("We don't have yet annex repo here")
            if vcs.get_file_key(relativepath):
                # FLOW GUIDE EXIT POINT
                # this is an annex'ed file -> get it
                # TODO implement `copy --from` using `source`
                # TODO fail if `source` is something strange
                vcs.get(relativepath)
                # return the absolute path to the installed file
                return path

        except FileInGitError:
            ###################################################
            # FLOW GUIDE
            #
            # `path` is either
            # - a  file already checked into Git
            # - known submodule
            ###################################################
            lgr.log(5, "FileInGitError logic")
            if source is not None:
                raise FileInGitError("File %s is already in git. Specifying source (%s) makes no sense"
                                     % (path, source))
            # file is checked into git directly -> nothing to do
            # OR this is a submodule of this dataset
            submodule = [sm for sm in ds.repo.get_submodules()
                         if sm.path == relativepath]
            if not len(submodule):
                # FLOW GUIDE EXIT POINT
                # this is a file in Git and no submodule, just return its path
                lgr.debug("Don't act, data already present in Git")
                return path
            elif len(submodule) > 1:
                raise RuntimeError(
                    "more than one submodule registered at the same path?")
            submodule = submodule[0]

            # FLOW GUIDE EXIT POINT
            # we are dealing with a known submodule (i.e. `source`
            # doesn't matter) -> check it out
            lgr.debug("Install subdataset at: {0}".format(submodule.path))
            subds = _install_subds_from_flexible_source(
                ds, submodule.path, submodule.url, recursive=recursive)
            return subds

        except FileNotInAnnexError:
            ###################################################
            # FLOW GUIDE
            #
            # `path` is either
            # - content of a subdataset
            # - an untracked file in this dataset
            # - an entire untracked/unknown existing subdataset
            ###################################################
            lgr.log(5, "FileNotInAnnexError logic")
            subds = ds.get_containing_subdataset(relativepath)
            if ds.path != subds.path:
                # FLOW GUIDE EXIT POINT
                # target path belongs to a known subdataset, hand
                # installation over to it
                return subds.install(
                    path=relpath(path, start=subds.path),
                    source=source,
                    recursive=recursive,
                    add_data_to_git=add_data_to_git)

            # FLOW GUIDE
            # this must be an untracked/existing something, so either
            # - a file
            # - a directory
            # - an entire repository
            if exists(opj(path, '.git')):
                # FLOW GUIDE EXIT POINT
                # this is an existing repo and must be in-place turned into
                # a submodule of this dataset
                return _install_subds_inplace(
                    ds, path, relativepath)

            # FLOW GUIDE EXIT POINT
            # - untracked file or directory in this dataset
            if isdir(path) and not recursive:
                # this is a directory and we want --recursive for it
                raise ValueError(
                    "installation of a directory requires the `recursive` flag")

            # few sanity checks
            if source and abspath(source) != path:
                raise ValueError(
                    "installation target already exists, but `source` points to "
                    "another location (target: '{0}', source: '{0}'".format(
                        source, path))

            if not add_data_to_git and not (isinstance(vcs, AnnexRepo)):
                raise RuntimeError(
                    "Trying to install file(s) into a dataset "
                    "with a plain Git repository. First initialize annex, or "
                    "provide override flag.")

            # switch `add` procedure between Git and Git-annex according to flag
            if add_data_to_git:
                vcs.add(relativepath, git=True)
                added_files = resolve_path(relativepath, ds)
            else:
                # do a blunt `annex add`
                added_files = vcs.add(relativepath)
                # return just the paths of the installed components
                if isinstance(added_files, list):
                    added_files = [resolve_path(i['file'], ds) for i in added_files]
                else:
                    added_files = resolve_path(added_files['file'], ds)
            if added_files:
                return added_files
            else:
                return None

        except IOError:
            ###################################################
            # FLOW GUIDE
            #
            # more complicated special cases -- `path` is either
            # - a file/subdataset in a not yet initialized but known
            #   submodule
            # - an entire untracked/unknown existing subdataset
            # - non-existing content that should be installed from `source`
            ###################################################
            lgr.log(5, "IOError logic")
            # we can end up here in two cases ATM
            if (exists(path) or islink(path)) or source is None:
                # FLOW GUIDE
                # - target exists but this dataset's VCS rejects it,
                #   so it should be part of a subdataset
                # or
                # - target doesn't exist, but no source is given, so
                #   it could be a handle that is actually contained in
                #   a not yet installed subdataset
                subds = ds.get_containing_subdataset(relativepath)
                if ds.path != subds.path:
                    # FLOW GUIDE
                    # target path belongs to a subdataset, hand installation
                    # over to it
                    if not subds.is_installed():
                        # FLOW GUIDE
                        # we are dealing with a target in a not yet
                        # available but known subdataset -> install it first
                        ds.install(subds.path, recursive=recursive)
                    return subds.install(
                        path=relpath(path, start=subds.path),
                        source=source,
                        recursive=recursive,
                        add_data_to_git=add_data_to_git)

                # FLOW GUIDE EXIT POINT
                raise InsufficientArgumentsError(
                    "insufficient information for installation: the "
                    "installation target {0} doesn't exists, isn't a "
                    "known part of dataset {1}, and no `source` "
                    "information was provided.".format(path, ds))

            if not source:
                # FLOW GUIDE EXIT POINT
                raise InsufficientArgumentsError(
                    "insufficient information for installation: the "
                    "installation target {0} doesn't exists, isn't a "
                    "known part of dataset {1}, and no `source` "
                    "information was provided.".format(path, ds))

            source_path = expandpath(source)
            if exists(source_path):
                # FLOW GUIDE EXIT POINT
                # this could be
                # - local file
                # - local directory
                # - repository outside the dataset
                # we only want to support the last case of locally cloning
                # a repo -- fail otherwise
                if exists(opj(source_path, '.git')):
                    return _install_subds_from_flexible_source(
                        ds, relativepath, source_path, recursive)

                raise ValueError(
                    "installing individual local files or directories is not "
                    "supported, copy/move them into the dataset first")

            # FLOW GUIDE
            # `source` is non-local, it could be:
            #   - repository
            #   - file
            # we have no further evidence, hence we need to try
            try:
                # FLOW GUIDE EXIT POINT
                # assume it is a dataset
                return _install_subds_from_flexible_source(
                    ds, relativepath, source, recursive)
            except CommandError:
                # FLOW GUIDE EXIT POINT
                # apaarently not a repo, assume it is a file url
                vcs.add_url_to_file(relativepath, source)
                return path

    @staticmethod
    def _get_new_vcs(ds, source):
        if source is None:
            raise RuntimeError(
                "No `source` was provided. To create a new dataset "
                "use the `create` command.")
        else:
            # when obtained from remote, try with plain Git
            lgr.info("Creating a new git repo at %s", ds.path)
            vcs = GitRepo(ds.path, url=source, create=True)
            if knows_annex(ds.path):
                # init annex when traces of a remote annex can be detected
                lgr.info("Initializing annex repo at %s", ds.path)
                vcs = AnnexRepo(ds.path, init=True)
            else:
                lgr.debug("New repository clone has no traces of an annex")
        return vcs

    @staticmethod
    def result_renderer_cmdline(res):
        from datalad.ui import ui
        if res is None:
            res = []
        if not isinstance(res, list):
            res = [res]
        if not len(res):
            ui.message("Nothing was installed")
            return
        items = '\n'.join(map(str, res))
        msg = "{n} installed {obj} available at\n{items}".format(
            obj='items are' if len(res) > 1 else 'item is',
            n=len(res),
            items=items)
        ui.message(msg)
