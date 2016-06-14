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

from datalad.support.constraints import EnsureStr
from datalad.support.constraints import EnsureNone
from datalad.support.exceptions import InsufficientArgumentsError
from datalad.support.gitrepo import GitRepo
from datalad.support.param import Parameter
from datalad.distribution.dataset import Dataset
from datalad.distribution.dataset import EnsureDataset
from datalad.distribution.dataset import datasetmethod
from datalad.utils import getpwd

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
        message=Parameter(
            args=("message",),
            metavar='MESSAGE',
            doc="""a message to annotate the saved state.""",
            constraints=EnsureStr()),
        auto_add_changes=Parameter(
            args=("-a", "--auto-add-changes"),
            doc="""automatically include all changes""",
            action="store_true"),
        version_tag=Parameter(
            args=("--version-tag", ),
            metavar='ID',
            doc="""an additional marker for that state.""",
            constraints=EnsureStr() | EnsureNone()),)

    @staticmethod
    @datasetmethod(name='save')
    def __call__(message, dataset=None, auto_add_changes=True, version_tag=None):

        # shortcut
        ds = dataset

        if ds is not None and not isinstance(ds, Dataset):
            ds = Dataset(ds)

        if ds is None:
            # try CWD:
            dspath = GitRepo.get_toppath(getpwd())
            if not dspath:
                raise InsufficientArgumentsError("No dataset found")
            ds = Dataset(dspath)

        if not ds.is_installed():
            raise RuntimeError(
                "cannot save a state when a dataset is not yet installed")
        if auto_add_changes:
            ds.repo.add('.')
            ds.repo.add('.', git=True)
        ds.repo.commit(message)
        if version_tag:
            ds.repo._git_custom_command('', 'git tag "{0}"'.format(version_tag))

        # TODO: Should save return the commit SHA?
