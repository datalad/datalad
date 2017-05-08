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
from datalad.support.constraints import EnsureChoice
from datalad.support.constraints import EnsureNone
from datalad.support.param import Parameter
from datalad.support.exceptions import CommandError
from datalad.support.exceptions import InsufficientArgumentsError
from datalad.interface.common_opts import recursion_flag
from datalad.interface.common_opts import recursion_limit
from datalad.distribution.dataset import require_dataset
from datalad.utils import swallow_logs

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
        mode=Parameter(
            args=('mode',),
            nargs='?',
            metavar='MODE',
            doc="""mode""",
            constraints=EnsureChoice('query', 'add', 'remove', 'configure') | EnsureNone()),

        ## actions
        # add gh-1235
        # remove gh-1483
        # query (implied)
        # configure gh-1235

        ## info options
        # --description gh-1484
        # --template/cfgfrom gh-1462 (maybe also for a one-time inherit)
        # --wanted gh-925 (also see below for add_sibling approach)

        ## same as add_sibling
        # --url
        # --pushurl
        # --fetch

        #as_common_datasrc=as_common_datasrc,
        #publish_depends=publish_depends,
        #publish_by_default=publish_by_default,
        #annex_wanted=annex_wanted_opt,
        #annex_group=annex_group_opt,
        #annex_groupwanted=annex_groupwanted_opt,
        #inherit=inherit_opt

        recursive=recursion_flag,
        recursion_limit=recursion_limit)

    @staticmethod
    @datasetmethod(name='siblings')
    @eval_results
    def __call__(
            mode='query',
            dataset=None,
            name=None,
            recursive=False,
            recursion_limit=None):
        # TODO catch invalid mode specified
        mode_worker_map = {
            'query': _query_remotes,
            'add': _add_remote,
            'configure': _configure_remote,
            'remove': _remove_remote,
        }
        worker = mode_worker_map[mode]

        dataset = require_dataset(
            dataset, check_installed=False, purpose='sibling configuration')
        refds_path = dataset.path

        res_kwargs = dict(refds=refds_path)

        # do not form single list of datasets (with recursion results) to
        # give fastest possible response, for the precise of a long-all
        # function call
        ds = dataset
        for r in worker(
                # always copy signature to below to avoid bugs!
                ds, name, **res_kwargs):
            yield r
        if not recursive:
            return

        for ds in dataset.subdatasets(
                fulfilled=True,
                recursive=recursive, recursion_limit=recursion_limit,
                result_xfm='datasets'):
            for r in worker(
                    # always copy signature from above to avoid bugs
                    ds, name, **res_kwargs):
                yield r


def _add_remote(
        ds, name, **res_kwargs):
    # it seems that the only difference is that `add` should fail if a remote
    # already exists
    if name in ds.repo.get_remotes():
        yield get_status_dict(
            action='add-sibling',
            status='error',
            path=ds.path,
            type_='sibling',
            name=name,
            message=("sibling is already known: %s", name),
            **res_kwargs)
        return
    for r in _configure_remote(ds, name, **res_kwargs):
        yield r


def _configure_remote(
        ds, name, **res_kwargs):
    # cheat and pretend it is all new and shiny already
    from datalad.distribution.add_sibling import AddSibling
    AddSibling.__call__(
        dataset=ds, name=None,
        url=url, pushurl=pushurl,
        # never recursive, done outside
        recursive=False,
        fetch=fetch,
        force=True,
        as_common_datasrc=None,
        publish_depends=None,
        publish_by_default=None,
        annex_wanted=None,
        annex_group=None,
        annex_groupwanted=None,
        inherit=False)


def _query_remotes(
        ds, name, **res_kwargs):
    remotes = [name] if name else ds.repo.get_remotes()
    for remote in remotes:
        info = get_status_dict(
            action='query-sibling',
            status='ok',
            path=ds.path,
            type_='sibling',
            name=remote,
            **res_kwargs)
        # now pull everything we know out of the config
        # simply because it is cheap and we don't have to go through
        # tons of API layers to be able to work with it
        for remotecfg in [k for k in ds.config.keys()
                          if k.startswith('remote.{}.'.format(remote))]:
            info[remotecfg[8 + len(remote):]] = ds.config[remotecfg]
        yield info


def _remove_remote(
        ds, name, **res_kwargs):
    if not name:
        # TODO we could do ALL instead, but that sounds dangerous
        raise InsufficientArgumentsError("no sibling name given")
    result_props = dict(
        action='remove-sibling',
        path=ds.path,
        type_='sibling',
        name=name,
        **res_kwargs)
    try:
        # failure can happen and is OK
        with swallow_logs():
            ds.repo.remove_remote(name)
    except CommandError as e:
        if 'fatal: No such remote' in e.stderr:
            yield get_status_dict(
                # result-oriented! given remote is absent already
                status='notneeded',
                **result_props)
            return
        else:
            raise e

    yield get_status_dict(
        status='ok',
        **result_props)
