# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Distribution utility functions

"""

import logging
from os import linesep
from os.path import exists
from os.path import isdir
from os.path import join as opj
from os.path import islink
from os.path import isabs
from os.path import relpath
from os.path import curdir
from os.path import normpath

from six.moves.urllib.parse import quote as urlquote

from datalad.support.gitrepo import GitRepo
from datalad.support.gitrepo import GitCommandError
from datalad.support.annexrepo import AnnexRepo
from datalad.support.exceptions import PathOutsideRepositoryError
from datalad.support.exceptions import InstallFailedError
from datalad.support.network import DataLadRI
from datalad.support.network import URL
from datalad.support.network import RI
from datalad.support.network import PathRI
from datalad.dochelpers import exc_str
from datalad.utils import swallow_logs
from datalad.utils import rmtree
from datalad.utils import knows_annex
from datalad.utils import with_pathsep as _with_sep

from .dataset import Dataset

lgr = logging.getLogger('datalad.distribution.utils')


def _install_subds_inplace(ds, path, relativepath, name=None):
    """Register an existing repository in the repo tree as a submodule"""
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


# TODO: evolved to sth similar to get_containing_subdataset. Therefore probably
# should move into this one as an option. But: consider circular imports!
def install_necessary_subdatasets(ds, path, reckless):
    """Installs subdatasets of `ds`, that are necessary to obtain in order
    to have access to `path`.

    Gets the subdataset containing `path` regardless of whether or not it was
    already installed. While doing so, installs everything necessary in between
    the uppermost installed one and `path`.

    Note: `ds` itself has to be installed.

    Parameters
    ----------
    ds: Dataset
    path: str
    reckless: bool

    Returns
    -------
    Dataset
      the last (deepest) subdataset, that was installed
    """
    assert ds.is_installed()

    # figuring out what dataset to start with:
    start_ds = ds.get_containing_subdataset(path, recursion_limit=None)

    if start_ds.is_installed():
        return start_ds

    # we try to install subdatasets as long as there is anything to
    # install in between the last one installed and the actual thing
    # to get (which is `path`):
    cur_subds = start_ds

    # Note, this is not necessarily `ds`:
    # MIH: would be good to know why?
    cur_par_ds = cur_subds.get_superdataset()
    assert cur_par_ds is not None

    while not cur_subds.is_installed():
        lgr.info("Installing subdataset %s%s",
                 cur_subds,
                 ' in order to get %s' % path if cur_subds.path != path else '')
        # get submodule info
        submodules = cur_par_ds.repo.get_submodules()
        submodule = [sm for sm in submodules
                     if sm.path == relpath(cur_subds.path, start=cur_par_ds.path)][0]
        # install using helper that give some flexibility regarding where to
        # get the module from
        _install_subds_from_flexible_source(
            cur_par_ds,
            submodule.path,
            submodule.url,
            reckless)

        cur_par_ds = cur_subds

        # Note: PathOutsideRepositoryError should not happen here.
        # If so, there went something fundamentally wrong, so raise something
        # different, to not let the caller mix it up with a "regular"
        # PathOutsideRepositoryError from above. (Although it could be
        # detected via its `repo` attribute)
        try:
            cur_subds = \
                cur_subds.get_containing_subdataset(path, recursion_limit=None)
        except PathOutsideRepositoryError as e:
            raise RuntimeError("Unexpected failure: {0}".format(exc_str(e)))

    return cur_subds


def _get_git_url_from_source(source):
    """Return URL for cloning associated with a source specification

    For now just resolves DataLadRIs
    """
    # TODO: Probably RF this into RI.as_git_url(), that would be overridden
    # by subclasses or sth. like that
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


def _install_subds_from_flexible_source(ds, sm_path, sm_url, reckless):
    """Tries to obtain a given subdataset from several meaningful locations"""
    # compose a list of candidate clone URLs
    clone_urls = _get_flexible_source_candidates_for_submodule(
        ds, sm_path, sm_url)

    # now loop over all candidates and try to clone
    subds = Dataset(opj(ds.path, sm_path))
    try:
        clone_url = _clone_from_any_source(clone_urls, subds.path)
    except GitCommandError as e:
        raise InstallFailedError(
            msg="Failed to install %s from %s (%s)" % (
                subds, clone_urls, exc_str(e))
            )
    # do fancy update
    if sm_path in ds.get_subdatasets(absolute=False, recursive=False):
        lgr.debug("Update cloned subdataset {0} in parent".format(subds))
        ds.repo.update_submodule(sm_path, init=True)
    else:
        # submodule is brand-new and previously unknown
        ds.repo.add_submodule(sm_path, url=clone_url)
    _fixup_submodule_dotgit_setup(ds, sm_path)
    _handle_possible_annex_dataset(subds, reckless)
    return subds


def _get_tracking_source(ds):
    """Returns name and url of a potential configured source
    tracking remote"""
    vcs = ds.repo
    repo = vcs.repo
    # if we have a remote, let's check the location of that remote
    # for the presence of the desired submodule
    tracking_branch = repo.active_branch.tracking_branch()
    remote_name = None
    remote_url = ''
    if tracking_branch:
        # name of the default remote for the active branch
        remote_name = repo.active_branch.tracking_branch().remote_name
        remote_url = vcs.get_remote_url(remote_name, push=False)
    return remote_name, remote_url


def _get_flexible_source_candidates(src, base_url=None):
    """Get candidates to try cloning from.

    Primarily to mitigate the problem that git doesn't append /.git
    while cloning from non-bare repos over dummy protocol (http*).  Also to
    simplify creation of urls whenever base url and relative path within it
    provided

    Parameters
    ----------
    src : string or RI
      Full or relative (then considered within base_url if provided) path
    base_url : string or RI, optional

    Returns
    -------
    candidates : list of str
      List of RIs (path, url, ssh targets) to try to install from
    """
    candidates = []

    ri = RI(src)
    if isinstance(ri, PathRI) and not isabs(ri.path) and base_url:
        ri = RI(base_url)
        if ri.path.endswith('/.git'):
            base_path = ri.path[:-5]
            base_suffix = '.git'
        else:
            base_path = ri.path
            base_suffix = ''
        ri.path = normpath(opj(base_path, src, base_suffix))

    src = str(ri)

    candidates.append(src)
    if isinstance(ri, URL):
        if ri.scheme in {'http', 'https'}:
            # additionally try to consider .git:
            if not src.rstrip('/').endswith('/.git'):
                candidates.append(
                    '{0}/.git'.format(src.rstrip('/')))

    # TODO:
    # We need to provide some error msg with InstallFailedError, since now
    # it just swallows everything.
    # yoh: not sure if this comment applies here, but could be still applicable
    # outisde

    return candidates


def _get_flexible_source_candidates_for_submodule(ds, sm_path, sm_url=None):
    """Retrieve candidates from where to install the submodule

    Even if url for submodule is provided explicitly -- first tries urls under
    parent's module tracking branch remote.

    TODO: reconsider?  yoh just maintained prev behavior for now
    """
    clone_urls = []
    # if we have a remote, let's check the location of that remote
    # for the presence of the desired submodule
    remote_name, remote_url = _get_tracking_source(ds)

    # Directly on parent's ds url
    if remote_url:
        # attempt: submodule checkout at parent remote URL
        # We might need to quote sm_path portion, e.g. for spaces etc
        if isinstance(RI(remote_url), URL):
            sm_path_url = urlquote(sm_path)
        else:
            sm_path_url = sm_path

        clone_urls += [
            u for u in _get_flexible_source_candidates(sm_path_url, remote_url)
            if u not in clone_urls
            ]

    # attempt: provided (configured?) submodule URL
    # TODO: consider supporting DataLadRI here?  or would confuse
    #  git and we wouldn't want that (i.e. not allow pure git clone
    #  --recursive)
    if sm_url:
        clone_urls += _get_flexible_source_candidates(
            sm_url,
            remote_url if remote_url else ds.path)

    return clone_urls


def _clone_from_any_source(sources, dest):
    # should not be the case, but we need to distinguish between failure
    # of git-clone, due to existing target and an unsuccessful clone
    # attempt. See below.
    existed = dest and exists(dest)
    for source_ in sources:
        try:
            lgr.debug("Retrieving a dataset from URL: "
                      "{0}".format(source_))
            with swallow_logs():
                GitRepo(dest, url=source_, create=True)
            return source_  # do not bother with other sources if succeeded
        except GitCommandError as e:
            lgr.debug("Failed to retrieve from URL: "
                      "{0}".format(source_))
            if not existed and dest \
                    and exists(dest):
                lgr.debug("Wiping out unsuccessful clone attempt at "
                          "{}".format(dest))
                rmtree(dest)

            if source_ == sources[-1]:
                # Note: The following block is evaluated whenever we
                # fail even with the last try. Not nice, but currently
                # necessary until we get a more precise exception:
                ####################################
                # TODO: We may want to introduce a --force option to
                # overwrite the target.
                # TODO: Currently assuming if `existed` and there is a
                # GitCommandError means that these both things are connected.
                # Need newer GitPython to get stderr from GitCommandError
                # (already fixed within GitPython.)
                if existed:
                    # rudimentary check for an installed dataset at target:
                    # (TODO: eventually check for being the one, that this
                    # is about)
                    dest_ds = Dataset(dest)
                    if dest_ds.is_installed():
                        lgr.info("{0} appears to be installed already."
                                 "".format(dest_ds))
                        break
                    else:
                        lgr.warning("Target {0} already exists and is not "
                                    "an installed dataset. Skipped."
                                    "".format(dest))
                        # Keep original in debug output:
                        lgr.debug("Original failure:{0}"
                                  "{1}".format(linesep, exc_str(e)))
                        return None
                ##################

                # Re-raise if failed even with the last candidate
                lgr.debug("Unable to establish repository instance at "
                          "{0} from {1}"
                          "".format(dest, sources))
                raise


def _recursive_install_subds_underneath(ds, recursion_limit, reckless, start=None):
    content_by_ds = {}
    if isinstance(recursion_limit, int) and recursion_limit <= 0:
        return content_by_ds
    # loop over submodules not subdatasets to get the url right away
    # install using helper that give some flexibility regarding where to
    # get the module from
    for sub in ds.repo.get_submodules():
        subds = Dataset(opj(ds.path, sub.path))
        if start is not None and not subds.path.startswith(_with_sep(start)):
            # this one we can ignore, not underneath the start path
            continue
        if not subds.is_installed():
            try:
                lgr.info("Installing subdataset %s", subds.path)
                subds = _install_subds_from_flexible_source(
                    ds, sub.path, sub.url, reckless)
                # we want the entire thing, but mark this subdataset
                # as automatically installed
                content_by_ds[subds.path] = [curdir]
            except Exception as e:
                # skip, if we didn't manage to install subdataset
                lgr.warning(
                    "Installation of subdatasets %s failed, skipped", subds)
                lgr.debug("Installation attempt failed with exception: %s",
                          exc_str(e))
                continue
            # otherwise recurse
            # we can skip the start expression, we know we are within
            content_by_ds.update(_recursive_install_subds_underneath(
                subds,
                recursion_limit=recursion_limit - 1 if isinstance(recursion_limit, int) else recursion_limit,
                reckless=reckless
            ))
    return content_by_ds


def _handle_possible_annex_dataset(dataset, reckless):
    # in any case check whether we need to annex-init the installed thing:
    if knows_annex(dataset.path):
        # init annex when traces of a remote annex can be detected
        if reckless:
            lgr.debug(
                "Instruct annex to hardlink content in %s from local "
                "sources, if possible (reckless)", dataset.path)
            dataset.config.add(
                'annex.hardlink', 'true', where='local', reload=True)
        lgr.debug("Initializing annex repo at %s", dataset.path)
        repo = AnnexRepo(dataset.path, init=True)
        if reckless:
            repo._run_annex_command('untrust', annex_options=['here'])


def _save_installed_datasets(ds, installed_datasets):
    paths = [relpath(subds.path, ds.path) for subds in installed_datasets]
    paths_str = ", ".join(paths)
    msg = "installed subdataset{}: {}".format(
        "s" if len(paths_str) > 1 else "", paths_str)
    lgr.info("Saving possible changes to {0} - {1}".format(
        ds, msg))
    ds.save(
        files=paths,
        message='[DATALAD] ' + msg,
        auto_add_changes=False,
        recursive=False)

