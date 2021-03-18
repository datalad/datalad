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

from argparse import REMAINDER
from itertools import chain
from tempfile import mkdtemp

from datalad.cmd import NoCapture, StdOutErrCapture
from datalad.core.local.run import normalize_command

from datalad.distribution.dataset import (
    Dataset,
    EnsureDataset,
    datasetmethod,
    require_dataset,
)
from datalad.dochelpers import exc_str
from datalad.interface.base import (
    Interface,
    build_doc,
)
from datalad.interface.common_opts import (
    jobs_opt,
    recursion_flag,
    recursion_limit,
)
from datalad.interface.results import get_status_dict
from datalad.interface.utils import eval_results
from datalad.support.constraints import (
    EnsureBool,
    EnsureNone,
)
from datalad.support.parallel import (
    ProducerConsumerProgressLog,
    no_parentds_in_futures,
    no_subds_in_futures,
)
from datalad.support.param import Parameter
from datalad.utils import (
    SequenceFormatter,
    getpwd,
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
        # TODO: --diff  to provide `diff` record so any arbitrary  git reset --hard etc desire could be fulfilled
        bottomup=Parameter(
            args=("--bottomup",),
            action="store_true",
            doc="""whether to report subdatasets in bottom-up order along
            each branch in the dataset tree, and not top-down."""),
        # Extra options
        # TODO: should we just introduce --lower-recursion-limit aka --mindepth of find?
        subdatasets_only=Parameter(
            args=("-s", "--subdatasets-only"),
            action="store_true",
            doc="""whether to exclude top level dataset."""),
        passthrough=Parameter(  # TODO  could be of use for `run` as well
            args=("-p", "--passthrough"),
            action="store_true",
            doc="""For command line commands, pass-through their output to 
            the screen instead of capturing/returning as part of the result records."""),
        jobs=jobs_opt,
        # TODO: might want explicit option to either worry about 'safe_to_consume' setting for parallel
        # For now - always safe
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
            subdatasets_only=False,
            passthrough=False,
            jobs=None
            ):
        if not cmd:
            lgr.warning("No command given")
            return
        if python and len(cmd) > 1:
            # yoh decided to avoid unnecessary complication/inhomogeneity with support
            # of multiple Python commands for now
            raise ValueError(f"Please provide a single Python expression. Got {len(cmd)}: {cmd!r}")
        refds = require_dataset(
            dataset, check_installed=True, purpose='foreach execution')
        pwd = getpwd()  # Note: 'run' has some more elaborate logic for this
        subdatasets_it = refds.subdatasets(
            fulfilled=fulfilled, recursive=recursive, recursion_limit=recursion_limit,
            bottomup=bottomup,
            result_xfm='paths'
        )

        if subdatasets_only:
            datasets_it = subdatasets_it
        else:
            if bottomup:
                datasets_it = chain(subdatasets_it, [refds.path])
            else:
                datasets_it = chain([refds.path], subdatasets_it)

        if not python:
            protocol = NoCapture if passthrough else StdOutErrCapture

        def run_cmd(dspath):
            ds = Dataset(dspath)
            status_rec = get_status_dict(
                'foreach',
                ds=ds,
                path=ds.path,
                command=cmd
            )
            if not ds.is_installed():
                yield dict(
                    status_rec,
                    status="impossible",
                    message="not installed"
                )
                return
            # For consistent environment (Python) and formatting (command) similar to `run` one
            # But for Python command we provide actual ds and refds not paths
            placeholders = dict(
                pwd=pwd,
                ds=ds if python else ds.path,
                refds=refds if python else refds.path,
                # Check if the command contains "tmpdir" to avoid creating an
                # unnecessary temporary directory in most but not all cases.
                # Note: different from 'run' - not wrapping match within {} and doing str
                tmpdir=mkdtemp(prefix="datalad-run-") if "tmpdir" in str(cmd) else "")
            try:
                if python:
                    status_rec['results'] = eval(cmd[0], placeholders)
                else:
                    try:
                        cmd_expanded = format_command(cmd, **placeholders)
                    except KeyError as exc:
                        yield dict(
                            status_rec,
                            status='impossible',
                            message=('command has an unrecognized placeholder: %s', exc))
                        return
                    # TODO: avoid use of _git_runner
                    out = ds.repo._git_runner.run(cmd_expanded, protocol=protocol)
                    if not passthrough:
                        status_rec.update(out)
                status_rec['status'] = 'ok'
            except Exception as exc:
                # TODO: option to not swallow but reraise!
                status_rec['status'] = 'error'
                # TODO: there must be a better place for it since this one is not
                # output by -f json_pp ... a feature or a bug???
                status_rec['message'] = exc_str(exc)
            yield status_rec

        yield from ProducerConsumerProgressLog(
            datasets_it,
            run_cmd,
            # probably not needed
            # It is ok to start with subdatasets since top dataset already exists
            safe_to_consume=no_subds_in_futures if bottomup else no_parentds_in_futures,
            # or vise versa
            label="foreach",
            unit="datasets",
            jobs=jobs,
            # TODO: regardless of either we provide lgr or not, we get progress bar.
            # But in "passthrough" mode output is likely to interfere.  So ideally we should
            # completely disable progress logging, and for that we should improve
            # ProducerConsumerProgressLog to allow for that
            lgr=lgr
        )


# Reduced version from run
def format_command(command, **kwds):
    """Plug in placeholders in `command`.

    Parameters
    ----------
    dset : Dataset
    command : str or list

    `kwds` is passed to the `format` call.

    Returns
    -------
    formatted command (str)
    """
    command = normalize_command(command)
    sfmt = SequenceFormatter()
    return sfmt.format(command, **kwds)