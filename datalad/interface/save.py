# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""For now just a wrapper for Dataset.save()

"""

__docformat__ = 'restructuredtext'

import logging

import os
from os.path import join as opj, isdir, realpath, relpath

from datalad.support.constraints import EnsureStr
from datalad.support.constraints import EnsureNone
from datalad.support.param import Parameter
from datalad.distribution.dataset import Dataset
from datalad.distribution.dataset import EnsureDataset
from datalad.distribution.dataset import datasetmethod
from datalad.distribution.dataset import require_dataset
from datalad.distribution.dataset import resolve_path
from datalad.distribution.utils import _install_subds_inplace
from datalad.interface.common_opts import recursion_limit, recursion_flag
from datalad.utils import assure_list
from datalad.utils import with_pathsep as _with_sep

from .base import Interface

lgr = logging.getLogger('datalad.interface.commit')


def untracked_subdatasets_to_submodules(ds, consider_paths):
    # treat special case of still untracked subdatasets.
    # those need to become submodules now, as they are otherwise added
    # without an entry in .gitmodules, and subsequently break Git's
    # submodule functionality completely
    _modified_flag = False
    if not consider_paths:
        # nothing to test
        return False

    for utf in ds.repo.repo.untracked_files:
        utf_abspath = opj(ds.path, utf)
        if not isdir(utf_abspath):
            # this cannot be a repository
            continue

        # test whether the potential submodule is scheduled for saving
        utf_realpath = realpath(utf_abspath)
        if any([utf_realpath.startswith(_with_sep(realpath(f)))
                for f in consider_paths]):
            # matches at least one path -> turn into submodule
            _install_subds_inplace(
                ds=ds,
                path=utf_abspath,  # can be ignored, we don't need the return value
                relativepath=utf.rstrip(os.sep),
                name=None)
            _modified_flag = True

    return _modified_flag


def deinit_deleted_submodules(ds):
    # helper to inspect a repo and `deinit` all submodules that are reported
    # as present, but the mountpoint doesn't exist
    deleted = ds.repo.get_deleted_files()
    for subdspath in ds.get_subdatasets(absolute=False, recursive=False):
        if subdspath in deleted:
            lgr.debug('deinit deleted subdataset {} in {}'.format(subdspath, ds))
            ds.repo.deinit_submodule(subdspath)


class Save(Interface):
    """Save the current state of a dataset

    Saving the state of a dataset records all changes that have been made
    to it. This change record is annotated with a user-provided description.
    Optionally, an additional tag, such as a version, can be assigned to the
    saved state. Such tag enables straightforward retrieval of past versions
    at a later point in time.

    || PYTHON >>
    Returns
    -------
    commit or None
      `None` if nothing was saved, the resulting commit otherwise.
    << PYTHON ||
    """

    _params_ = dict(
        dataset=Parameter(
            args=("-d", "--dataset"),
            doc=""""specify the dataset to save. If
            no dataset is given, an attempt is made to identify the dataset
            based on the current working directory.""",
            constraints=EnsureDataset() | EnsureNone()),
        files=Parameter(
            args=("files",),
            metavar='FILES',
            doc="""list of files to consider. If given, only changes made
            to those files are recorded in the new state.""",
            nargs='*',
            constraints=EnsureStr() | EnsureNone()),
        message=Parameter(
            args=("-m", "--message",),
            metavar='MESSAGE',
            doc="""a message to annotate the saved state.""",
            constraints=EnsureStr() | EnsureNone()),
        auto_add_changes=Parameter(
            args=("-a", "--auto-add-changes"),
            doc="""automatically include all changes in the entire dataset,
            independent of the current working directory.""",
            action="store_true"),
        version_tag=Parameter(
            args=("--version-tag", ),
            metavar='ID',
            doc="""an additional marker for that state.""",
            constraints=EnsureStr() | EnsureNone()),
        recursive=recursion_flag,
        recursion_limit=recursion_limit,
    )

    @staticmethod
    @datasetmethod(name='save')
    def __call__(message=None, files=None, dataset=None,
                 auto_add_changes=False, version_tag=None,
                 recursive=False, recursion_limit=None):
        # shortcut
        ds = require_dataset(dataset, check_installed=True,
                             purpose='saving')

        if not ds.repo.repo.is_dirty(
                index=True,
                working_tree=True,
                untracked_files=True,
                submodules=True):
            # if we cannot see anything dirty at all, the only things we could
            # do is tag
            if version_tag:
                ds.repo.tag(version_tag)
            # take the easy one out
            return

        # always yields list; empty if None
        files = assure_list(files)

        # before anything, let's deal with missing submodules that may have
        # been rm'ed by the user
        # this will not alter/amend the history of the dataset
        deinit_deleted_submodules(ds)

        # XXX path resolution needs to happen on the input argument, not the
        # resolved dataset!
        # otherwise we will not be able to figure out, whether there was an
        # explicit dataset provided, or just a matching one resolved
        # automatically.
        # if files are provided but no dataset, we interpret them as
        # CWD-related

        if auto_add_changes:
            # use the dataset's base path to indiciate that everything
            # should be saved
            files = [ds.path]
        else:
            # make sure we apply the usual path interpretation logic
            files = [resolve_path(p, dataset) for p in files]

        # track whether we modified anything, so it becomes
        # possible to decide when/what to save further down
        # and one level up
        _modified_flag = False

        _modified_flag = untracked_subdatasets_to_submodules(
            ds, files) or _modified_flag

        # now we should have a complete list of submodules to potentially
        # recurse into
        if recursive and (recursion_limit is None or recursion_limit > 0):
            # what subdataset to touch?
            subdss = []
            if auto_add_changes:
                # all installed 1st-level ones
                # we only want immediate subdatasets, higher depths will come via
                # recursion
                subdss = [Dataset(opj(ds.path, subds_path))
                          for subds_path in ds.get_subdatasets(
                              recursive=False)]
            elif files is not None:
                # only subdatasets that contain any of the to-be-considered
                # paths
                subdss = [ds.get_containing_subdataset(
                    p, recursion_limit=1) for p in files]
            # skip anything that isn't installed, or this dataset
            subdss = [d for d in subdss if d.is_installed() and d != ds]

            prop_recursion_limit = \
                None if recursion_limit is None else max(recursion_limit - 1, 0)
            for subds in subdss:
                subds_modified = Save.__call__(
                    message=message,
                    files=[f for f in files
                           if ds.get_containing_subdataset(
                               f, recursion_limit=1) == subds],
                    dataset=subds,
                    auto_add_changes=auto_add_changes,
                    version_tag=version_tag,
                    recursive=recursive and (prop_recursion_limit is None or prop_recursion_limit > 0),
                    recursion_limit=prop_recursion_limit,
                )
                if subds_modified:
                    # stage changes in this submodule
                    ds.repo.add(relpath(subds.path, ds.path),
                                git=True)
                    _modified_flag = True

        if files:  # could still be none without auto add changes
            absf = [f for f in files
                    if ds.get_containing_subdataset(f, recursion_limit=1) == ds]
            if len(absf):
                # XXX Is there a better way to handle files in mixed repos?
                ds.repo.add(absf)
                ds.repo.add(absf, git=True)

        _datalad_msg = False
        if not message:
            message = 'Recorded existing changes'
            _datalad_msg = True

        # anything should be staged by now
        # however, staged submodule changes are not considered as
        # `index`, hence `submodules` needs to be True too
        if ds.repo.repo.is_dirty(
                index=True,
                working_tree=False,
                untracked_files=False,
                submodules=True):
            ds.repo.commit(message, _datalad_msg=_datalad_msg)
            _modified_flag = True
        elif not auto_add_changes:
            lgr.info(
                'Nothing to save, consider auto-detection of changes, '
                'if this is unexpected.')
        # MIH: let's tag even if there was nothing commit. I'd forget this
        # option too often...
        if version_tag:
            ds.repo.tag(version_tag)

        return ds.repo.repo.head.commit if _modified_flag else None

    @staticmethod
    def result_renderer_cmdline(res, args):
        from datalad.ui import ui
        if res:
            ui.message('Saved state: "{0}" by {1} [{2}]'.format(
                res.message.splitlines()[0],
                res.committer,
                res.hexsha))
