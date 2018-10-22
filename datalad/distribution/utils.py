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

from os.path import join as opj
from os.path import isabs
from os.path import normpath
import posixpath

from six.moves.urllib.parse import unquote as urlunquote

from datalad.support.annexrepo import GitRepo
from datalad.support.annexrepo import AnnexRepo
from datalad.support.network import DataLadRI
from datalad.support.network import URL
from datalad.support.network import RI
from datalad.support.network import PathRI
from datalad.utils import knows_annex


lgr = logging.getLogger('datalad.distribution.utils')


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
    if not knows_annex(dataset.path):
        # not for us
        return

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
    # go through list of special remotes and issue info message that
    # some additional ones are present and were not auto-enabled
    remote_names = repo.get_remotes(
        with_urls_only=False,
        exclude_special_remotes=False)
    for k, v in repo.get_special_remotes().items():
        sr_name = v.get('name', None)
        if sr_name and sr_name not in remote_names:
            # if it is not listed among the remotes, it wasn't enabled
            lgr.info(
                'access to dataset sibling "%s" not auto-enabled, enable with:\n\t\tdatalad siblings -d "%s" enable -s %s',
                sr_name,
                dataset.path,
                sr_name)


def _get_installationpath_from_url(url):
    """Returns a relative path derived from the trailing end of a URL

    This can be used to determine an installation path of a Dataset
    from a URL, analog to what `git clone` does.
    """
    ri = RI(url)
    if isinstance(ri, (URL, DataLadRI)):  # decode only if URL
        path = ri.path.rstrip('/')
        path = urlunquote(path) if path else ri.hostname
    else:
        path = url
    path = path.rstrip('/')
    if '/' in path:
        path = path.split('/')
        if path[-1] == '.git':
            path = path[-2]
        else:
            path = path[-1]
    if path.endswith('.git'):
        path = path[:-4]
    return path
