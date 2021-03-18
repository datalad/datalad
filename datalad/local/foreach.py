# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Plumbing command for running a command on each (sub)dataset"""

__docformat__ = 'restructuredtext'


import logging
import os
import re

from argparse import REMAINDER

from datalad.interface.base import Interface
from datalad.interface.utils import eval_results
from datalad.interface.base import build_doc
from datalad.interface.results import get_status_dict
from datalad.support.constraints import (
    EnsureBool,
    EnsureStr,
    EnsureNone,
)
from datalad.support.param import Parameter
from datalad.support.exceptions import CommandError
from datalad.interface.common_opts import (
    jobs_opt,
    recursion_flag,
    recursion_limit,
)
from datalad.distribution.dataset import (
    Dataset,
    require_dataset,
)
from datalad.support.gitrepo import GitRepo
from datalad.dochelpers import exc_str
from datalad.utils import (
    ensure_list,
    getpwd,
    partition,
    Path,
)

from datalad.distribution.dataset import (
    EnsureDataset,
    datasetmethod,
    resolve_path,
)

lgr = logging.getLogger('datalad.local.foreach')


@build_doc
class ForEach(Interface):
    r"""Run a command on the dataset and/or each of its sub-datasets.

    Each dataset's repo runner is reused to execute the commands, so they
    are are executed in the top directory of a corresponding dataset.
    In contrast, Python commands (expressions) are evaluated without changing directory.
    TODO: unify via explicit --chdir? but not sure if worth it

    WARNING: Python expressions are `eval`ed within the scope of this process
    and provided existing objects.

    """
    # TODO:     _examples_ = [], # see e.g. run

    _params_ = dict(
        cmd=Parameter(
            args=("cmd",),
            nargs=REMAINDER,
            metavar='COMMAND',
            doc="""command for execution. A leading '--' can be used to
            disambiguate this command from the preceding options to DataLad."""),
        python=Parameter(
            args=("--python",),
            action="store_true",
            doc="""if given, must be a boolean flag indicating whether
            the `cmd` is Python expressions to be evaluated, instead of
            an external command to be executed"""),
        # Following options are taken from subdatasets
        dataset=Parameter(
            args=("-d", "--dataset"),
            doc="""specify the dataset to operate on.  If
            no dataset is given, an attempt is made to identify the dataset
            based on the input and/or the current working directory""",
            constraints=EnsureDataset() | EnsureNone()),
        # TODO: assume True since in 99% of use cases we just want to operate
        #  on present subdatasets?  but having it explicit could be good to
        #  "not miss any".  But `--fulfilled true` is getting on my nerves
        fulfilled=Parameter(
            args=("--fulfilled",),
            doc="""if given, must be a boolean flag indicating whether
            to report either only locally present or absent datasets.
            By default subdatasets are reported regardless of their
            status""",
            constraints=EnsureBool() | EnsureNone()),
        recursive=recursion_flag,
        recursion_limit=recursion_limit,
        #TODO: passthrough - to instruct to not catch/yield outputs but rather just run as `run`
        # does without any outputs handling
        # Not sure yet if worth supporting here
        # contains=Parameter(
        #     args=('--contains',),
        #     metavar='PATH',
        #     action='append',
        #     doc="""limit report to the subdatasets containing the
        #     given path. If a root path of a subdataset is given the last
        #     reported dataset will be the subdataset itself.[CMD:  This
        #     option can be given multiple times CMD][PY:  Can be a list with
        #     multiple paths PY], in which case datasets will be reported that
        #     contain any of the given paths.""",
        #     constraints=EnsureStr() | EnsureNone()),
        bottomup=Parameter(
            args=("--bottomup",),
            action="store_true",
            doc="""whether to report subdatasets in bottom-up order along
            each branch in the dataset tree, and not top-down."""),
        # Extra options
        jobs=jobs_opt,
    )

    @staticmethod
    @datasetmethod(name='foreach')
    @eval_results
    def __call__(
            cmd=None,
            python=False,
            dataset=None,
            fulfilled=None,
            recursive=False,
            recursion_limit=None,
            # contains=None,
            bottomup=False,
            jobs=None
            ):
        if not cmd:
            lgr.warning("No command given")
            return
        if python and len(cmd) > 1:
            # yoh decided to avoid unnecessary complication/inhomogeneity with support
            # of multiple Python commands for now
            raise ValueError(f"Please provide a single Python expression. Got {len(cmd)}: {cmd!r}")
        ds = require_dataset(
            dataset, check_installed=True, purpose='foreach execution')
        subdatasets_it = ds.subdatasets(
            fulfilled=fulfilled, recursive=recursive, recursion_limit=recursion_limit,
            bottomup=bottomup,
        )
        # TODO: chain with ds
        for ds_rec in subdatasets_it:
            ds_ = Dataset(ds_rec['path'])
            status_rec = get_status_dict(
                'foreach',
                ds=ds_,
                path=ds_.path,
                command=cmd
            )
            if not ds_.is_installed():
                status_rec['status'] = 'impossible'
                status_rec['message'] = 'not installed'
            else:
                try:
                    if python:
                        out = []
                        # TODO: harmonize with placeholders of `run`
                        out.append(
                            eval(cmd[0],
                                {
                                    'refds': ds,
                                    'ds': ds_
                                }
                            )
                        )
                        status_rec['results'] = out
                    else:
                        # TODO: provide .format()ing of `run`
                        # TODO: avoid use of _git_runner
                        out = ds_.repo._git_runner.run(cmd)
                        status_rec.update(out)
                    status_rec['status'] = 'ok'
                except Exception as exc:
                    # TODO: option to not swallow but reraise!
                    status_rec['status'] = 'error'
                    # TODO: there must be a better place for it since this one is not
                    # output by -f json_pp ... a feature or a bug???
                    status_rec['message'] = exc_str(exc)
            yield status_rec

        """
        yield from ProducerConsumerProgressLog(
            subdatasets_gen,  # chain with current one depending on topdown
            action,
            # probably not needed
            # It is ok to start with subdatasets since top dataset already exists
            safe_to_consume=no_parentds_in_futures if topdown else no_subds_in_futures, # or vise versa
            jobs=jobs
       )
       """