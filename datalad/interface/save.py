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

from os.path import abspath, join as opj, isdir, realpath, relpath

from datalad.support.constraints import EnsureStr
from datalad.support.constraints import EnsureNone
from datalad.support.param import Parameter
from datalad.distribution.dataset import Dataset
from datalad.distribution.dataset import EnsureDataset
from datalad.distribution.dataset import datasetmethod
from datalad.distribution.dataset import require_dataset
from datalad.distribution.dataset import _with_sep
from datalad.distribution.install import _install_subds_inplace
from datalad.interface.common_opts import recursion_limit, recursion_flag

from .base import Interface

lgr = logging.getLogger('datalad.interface.commit')


def untracked_subdatasets_to_submodules(ds, consider_paths):
    _modified_flag = False
    # treat special case of still untracked subdatasets.
    # those need to become submodules now, as they are otherwise added
    # without an entry in .gitmodules, and subsequently break Git's
    # submodule functionality completely
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
                relativepath=utf,
                name=None)
            _modified_flag = True

    return _modified_flag


class Save(Interface):
    """Save the current state of a dataset

    Saving the state of a dataset records all changes that have been made
    to it. This change record is annotated with a user-provided description.
    Optionally, an additional tag, such as a version, can be assigned to the
    saved state. Such tag enables straightforward retrieval of past versions
    at a later point in time.
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

        # use the dataset's base path to indiciate that everything
        # should be saved
        if auto_add_changes:
            files = [ds.path]

        # track whether we modified anything, so it becomes
        # possible to decide when/what to save further down
        # and one level up
        _modified_flag = False

        _modified_flag = untracked_subdatasets_to_submodules(
            ds, files)

        # now we should have a complete list of submodules to potentially
        # recurse into
        if recursive and (recursion_limit is None or recursion_limit):
            # we only want immediate subdatasets, higher depths will come via
            # recursion
            subdss = [Dataset(opj(ds.path, subds_path))
                      for subds_path in ds.get_subdatasets(
                          recursive=False)]
            # skip anything that isn't installed
            subdss = [d for d in subdss if d.is_installed()]
            for subds in subdss:
                subds_modified = Save.__call__(
                    message=message,
                    # TODO figure out which files to pass down
                    # borrow logic from `add`
                    files=files,
                    dataset=subds,
                    auto_add_changes=auto_add_changes,
                    version_tag=version_tag,
                    recursive=recursive,
                    recursion_limit=None if recursion_limit is None else recursion_limit - 1,
                )
                if subds_modified:
                    # stage changes in this submodule
                    ds.repo.add(relpath(subds.path, ds.path),
                                git=True)
                    _modified_flag = True

        if files:  # could still be none without auto add changes
            absf = [abspath(f) for f in files]
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

        return ds.repo.repo.head.commit if _modified_flag else False

    @staticmethod
    def result_renderer_cmdline(res, args):
        from datalad.ui import ui
        if res:
            ui.message('Saved state: "{0}" by {1} [{2}]'.format(
                res.message.splitlines()[0],
                res.committer,
                res.hexsha))
