# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Plumbing command for managing sibling configuration"""

__docformat__ = 'restructuredtext'


import logging

from datalad.interface.base import Interface
from datalad.interface.utils import eval_results
from datalad.interface.utils import build_doc
from datalad.interface.results import get_status_dict
from datalad.support.constraints import EnsureStr
from datalad.support.constraints import EnsureNone
from datalad.support.param import Parameter
from datalad.interface.common_opts import recursion_flag
from datalad.interface.common_opts import recursion_limit
from datalad.distribution.dataset import require_dataset

from .dataset import EnsureDataset
from .dataset import datasetmethod

lgr = logging.getLogger('datalad.distribution.siblings')


@build_doc
class Siblings(Interface):
    """

    The following properties are reported (if possible) for each matching
    subdataset record.

    "name"
        Name of the sibling

    "path"
        Absolute path of the dataset

    """
    _params_ = dict(
        dataset=Parameter(
            args=("-d", "--dataset"),
            doc="""specify the dataset to configure.  If
            no dataset is given, an attempt is made to identify the dataset
            based on the input and/or the current working directory""",
            constraints=EnsureDataset() | EnsureNone()),
        name=Parameter(
            args=('-s', '--name',),
            metavar='NAME',
            doc="""name of the sibling""",
            constraints=EnsureStr() | EnsureNone()),
        recursive=recursion_flag,
        recursion_limit=recursion_limit)

    @staticmethod
    @datasetmethod(name='siblings')
    @eval_results
    def __call__(
            dataset=None,
            name=None,
            recursive=False,
            recursion_limit=None):
        dataset = require_dataset(
            dataset, check_installed=False, purpose='sibling configuration')
        refds_path = dataset.path

        res_kwargs = dict(refds=refds_path)

        for r in _query_remotes(dataset, name, **res_kwargs):
            yield r
        if not recursive:
            return

        for ds in dataset.subdatasets(
                fulfilled=True,
                recursive=recursive, recursion_limit=recursion_limit,
                result_xfm='datasets'):
            for r in _query_remotes(ds, name, **res_kwargs):
                yield r


def _query_remotes(ds, name, **kwargs):
    remotes = [name] if name else ds.repo.get_remotes()
    for remote in remotes:
        info = get_status_dict(
            action='sibling',
            status='ok',
            ds=ds,
            name=remote,
            **kwargs)
        # now pull everything we know out of the config
        # simply because it is cheap and we don't have to go through
        # tons of API layers to be able to work with it
        for remotecfg in [k for k in ds.config.keys()
                          if k.startswith('remote.{}.'.format(remote))]:
            info[remotecfg[8 + len(remote):]] = ds.config[remotecfg]
        yield info
