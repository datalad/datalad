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

from datalad.support.network import (
    PathRI,
    RI,
    URL,
    is_url,
    urlunquote,
)

from .create_sibling_github import _get_gh_reponame


lgr = logging.getLogger('datalad.distribution.utils')


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
        is_github = is_url(ri) \
            and (ri.hostname == 'github.com' or ri.hostname.endswith('.github.com'))

        if ri.path.endswith('/.git'):
            base_path = ri.path[:-5]
            base_suffix = '.git'
        elif is_github and ri.path.endswith('.git'):
            base_path = ri.path[:-4]
            base_suffix = '.git'
        else:
            base_path = ri.path
            base_suffix = ''

        if isinstance(ri, PathRI):
            # this is a path, so stay native
            ri.path = normpath(opj(base_path, src, base_suffix))
        else:
            # we are handling a URL, use POSIX path conventions unless github
            # which is known to not support more than two levels, so it makes no sense
            # to even try to try /lev1/lev2/lev3.
            if (is_github
                # for SSH RI it might not have leading `/` in the path, so react only if
                # there is `/` in the middle somewhere
                and ('/' in base_path.lstrip('/'))
            ):
                # Note: Outside code urlencodes path if a URL. To minimize github-support PR
                # we just urlunquote here and rely on our ad-hoc sanitization for github
                org_path, reponame = base_path.rsplit('/', 1)
                ri.path = posixpath.normpath(
                    opj(org_path,
                        _get_gh_reponame(reponame, urlunquote(src))  # follow our default preparation
                        + base_suffix   # github uses .git not /.git as well there
                        )
                )
            else:
                # straightforward POSIX
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

    return candidates
