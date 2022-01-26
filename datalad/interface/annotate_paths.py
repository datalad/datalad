# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Residual functionality to keep metadata implementation running
until metalad is ready"""

__docformat__ = 'restructuredtext'

import logging
from os.path import lexists
from pathlib import Path

from datalad.distribution.dataset import Dataset


lgr = logging.getLogger('datalad.interface.annotate_paths')


def _minimal_annotate_paths(paths_by_ds, errors, action="annotate_path",
                            recursive=None, recursion_limit=None, refds=None):
    """This is an internal helper to replace AnnotatePaths

    DO NOT USE IN ANY NEW CODE!!

    It supports only a fraction of the functionality, but enough to keep the
    metadata commands working. The goal is to remove it together with these
    metadata commands, when they are replaced by metalad
    """
    for e in errors:
        yield dict(
            action=action,
            path=str(e),
            status='error',
            message="path not associated with any dataset",
        )
    for dpath, paths in paths_by_ds.items():
        if paths is None:
            yield dict(
                action=action,
                path=str(dpath),
                status='',
                state='present',
                type='dataset',
                refds=refds,
                parentds=Dataset(dpath).get_superdataset(),
            )
            continue

        subdatasets = Dataset(dpath).subdatasets(
            path=paths,
            state='any',
            recursive=recursive,
            recursion_limit=recursion_limit,
            result_renderer='disabled',
            result_xfm=None)
        subdataset_paths = [Path(r['path']) for r in subdatasets]

        for p in paths:
            ptype = 'dataset' \
                if p == dpath or p in subdataset_paths \
                else 'directory' \
                if p.is_dir() \
                else 'file'
            if ptype == 'dataset':
                pstate = 'present' if p == dpath \
                    else [r.get('state') for r in subdatasets
                          if Path(r['path']) == p][0]
            else:
                pstate = 'present' if lexists(p) else 'absent'
            yield dict(
                action=action,
                path=str(p),
                status='',
                type=ptype,
                state=pstate,
                refds=refds,
                parentds=str(dpath),
            )
        if recursive:
            for sd in subdatasets:
                yield dict(
                    action=action,
                    path=sd['path'],
                    status='',
                    state=sd['state'],
                    type='dataset',
                    refds=refds,
                    parentds=sd.get('parentds'),
                )
