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

from os.path import abspath, join as opj, isdir, realpath

from datalad.support.constraints import EnsureStr
from datalad.support.constraints import EnsureNone
from datalad.support.param import Parameter
from datalad.distribution.dataset import EnsureDataset
from datalad.distribution.dataset import datasetmethod
from datalad.distribution.dataset import require_dataset
from datalad.distribution.dataset import _with_sep
from datalad.distribution.install import _install_subds_inplace

from .base import Interface

lgr = logging.getLogger('datalad.interface.commit')


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
            constraints=EnsureStr() | EnsureNone()),)

    @staticmethod
    @datasetmethod(name='save')
    def __call__(message=None, files=None, dataset=None,
                 auto_add_changes=False, version_tag=None):
        # shortcut
        ds = require_dataset(dataset, check_installed=True,
                             purpose='saving')

        if not message:
            message = 'Changes recorded by datalad'
        if auto_add_changes:
            files = [ds.path]

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
                    for f in files]):
                # matches at least one path -> turn into submodule
                _install_subds_inplace(
                    ds=ds,
                    path=utf_abspath,  # can be ignored, we don't need the return value
                    relativepath=utf,
                    name=None)

        if files:  # could still be none without auto add changes
            absf = [abspath(f) for f in files]
            # XXX Is there a better way to handle files in mixed repos?
            ds.repo.add(absf)
            ds.repo.add(absf, git=True)

        # anything should be staged by now
        # now however, that staged submodule changes are not considered as
        # `index`, hence `submodules` needs to be True too
        if ds.repo.repo.is_dirty(
                index=True,
                working_tree=False,
                untracked_files=False,
                submodules=True):
            ds.repo.commit(message)
        else:
            lgr.info(
                'Nothing to save, consider auto-detection of changes, '
                'if this is unexpected.')
        # MIH: let's tag even if there was nothing commit. I'd forget this
        # option too often...
        if version_tag:
            ds.repo.tag(version_tag)

        return ds.repo.repo.head.commit

    @staticmethod
    def result_renderer_cmdline(res, args):
        from datalad.ui import ui
        ui.message('Saved state: "{0}" by {1} [{2}]'.format(
            res.message.splitlines()[0],
            res.committer,
            res.hexsha))
