# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Distribution utility functions

"""

import logging
import posixpath
from os.path import isabs
from os.path import join as opj
from os.path import normpath

from datalad.log import log_progress
from datalad.support.annexrepo import AnnexRepo
from datalad.support.network import (
    RI,
    URL,
    PathRI,
)

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

    return candidates



def _yield_ds_w_matching_siblings(
        ds, names, recursive=False, recursion_limit=None):
    """(Recursively) inspect a dataset for siblings with particular name(s)

    Parameters
    ----------
    ds: Dataset
      The dataset to be inspected.
    names: iterable
      Sibling names (str) to test for.
    recursive: bool, optional
      Whether to recurse into subdatasets.
    recursion_limit: int, optional
      Recursion depth limit.

    Yields
    ------
    str, str
      Path to the dataset with a matching sibling, and name of the matching
      sibling in that dataset.
    """

    def _discover_all_remotes(ds, refds, **kwargs):
        """Helper to be run on all relevant datasets via foreach
        """
        # Note, that `siblings` doesn't tell us about not enabled special
        # remotes. There could still be conflicting names we need to know
        # about in order to properly deal with the `existing` switch.

        repo = ds.repo
        # list of known git remotes
        if isinstance(repo, AnnexRepo):
            remotes = repo.get_remotes(exclude_special_remotes=True)
            remotes.extend([v['name']
                            for k, v in repo.get_special_remotes().items()]
                           )
        else:
            remotes = repo.get_remotes()
        return remotes

    if not recursive:
        for name in _discover_all_remotes(ds, ds):
            if name in names:
                yield ds.path, name
        return

    # in recursive mode this check could take a substantial amount of
    # time: employ a progress bar (or rather a counter, because we don't
    # know the total in advance
    pbar_id = 'check-siblings-{}'.format(id(ds))
    log_progress(
        lgr.info, pbar_id,
        'Start checking pre-existing sibling configuration %s', ds,
        label='Query siblings',
        unit=' Siblings',
    )

    for res in ds.foreach_dataset(
            _discover_all_remotes,
            recursive=recursive,
            recursion_limit=recursion_limit,
            return_type='generator',
            result_renderer='disabled',
    ):
        # unwind result generator
        if 'result' in res:
            for name in res['result']:
                log_progress(
                    lgr.info, pbar_id,
                    'Discovered sibling %s in dataset at %s',
                    name, res['path'],
                    update=1,
                    increment=True)
                if name in names:
                    yield res['path'], name

    log_progress(
        lgr.info, pbar_id,
        'Finished checking pre-existing sibling configuration %s', ds,
    )
