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
from os.path import exists
from os.path import isdir
from os.path import join as opj
from os.path import islink
from os.path import isabs
from os.path import normpath
import posixpath

from datalad.support.annexrepo import AnnexRepo
from datalad.support.network import DataLadRI
from datalad.support.network import URL
from datalad.support.network import RI
from datalad.support.network import PathRI
from datalad.utils import knows_annex


lgr = logging.getLogger('datalad.distribution.utils')


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

    dot_git = opj(path, ".git")
    if not exists(dot_git):
        raise RuntimeError("Missing .git in %s." % path)
    elif islink(dot_git):
        # readlink cannot be imported on windows, but there should also
        # be no symlinks
        from os import readlink
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


def _get_tracking_source(ds):
    """Returns name and url of a potential configured source
    tracking remote"""
    vcs = ds.repo
    # if we have a remote, let's check the location of that remote
    # for the presence of the desired submodule

    remote_name, tracking_branch = vcs.get_tracking_branch()
    # TODO: better default `None`? Check where we might rely on '':
    remote_url = ''
    if remote_name:
        remote_url = vcs.get_remote_url(remote_name, push=False)

    return remote_name, remote_url


def _get_flexible_source_candidates(src, base_url=None, alternate_suffix=True):
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
    alternate_suffix : bool
      Whether to generate URL candidates with and without '/.git' suffixes.

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
        if isinstance(ri, PathRI):
            # this is a path, so stay native
            ri.path = normpath(opj(base_path, src, base_suffix))
        else:
            # we are handling a URL, use POSIX path conventions
            ri.path = posixpath.normpath(
                posixpath.join(base_path, src, base_suffix))

    src = str(ri)

    candidates.append(src)
    if alternate_suffix and isinstance(ri, URL):
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


def _handle_possible_annex_dataset(dataset, reckless, description=None):
    """If dataset "knows annex" -- annex init it, set into reckless etc
    
    Provides additional tune up to a possibly an annex repo, e.g.
    "enables" reckless mode, sets up description
    """
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
        # XXX this is rather convoluted, init does init, but cannot
        # set a description without `create=True`
        repo = AnnexRepo(dataset.path, init=True)
        # so do manually see #1403
        if description:
            repo._init(description=description)
        if reckless:
            repo._run_annex_command('untrust', annex_options=['here'])


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
