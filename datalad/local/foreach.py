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
from datalad.interface.base import (
    Interface,
    build_doc,
)
from datalad.interface.common_opts import (
    contains,
    fulfilled,
    jobs_opt,
    recursion_flag,
    recursion_limit,
)
from datalad.interface.results import get_status_dict
from datalad.interface.utils import eval_results
from datalad.support.constraints import (
    EnsureChoice,
    EnsureNone,
)
from datalad.support.exceptions import InsufficientArgumentsError
from datalad.support.parallel import (
    ProducerConsumer,
    ProducerConsumerProgressLog,
    no_parentds_in_futures,
    no_subds_in_futures,
)
from datalad.support.param import Parameter
from datalad.utils import (
    SequenceFormatter,
    chpwd,
    getpwd,
    shortened_repr,
    swallow_outputs,
)

lgr = logging.getLogger('datalad.local.foreach')


_PYTHON_CMDS = {
    'exec': exec,
    'eval': eval
}


@build_doc
class ForEach(Interface):
    r"""Run a command or Python code on the dataset and/or each of its sub-datasets.

    This command provides a convenience for the cases were no dedicated DataLad command
    is provided to operate across the hierarchy of datasets. It is very similar to
    `git submodule foreach` command with the following major differences

    - by default (unless [CMD: --subdatasets-only][PY: `subdatasets_only=True`]) it would
      include operation on the original dataset as well,
    - subdatasets could be traversed in bottom-up order,
    - can execute commands in parallel (see `jobs` option), but would account for the order,
      e.g. in bottom-up order command is executed in super-dataset only after it is executed
      in all subdatasets.

    *Command format*

    || REFLOW >>
    [CMD: --cmd-type external CMD][PY: cmd_type='external' PY]: A few placeholders are
    supported in the command via Python format
    specification. "{pwd}" will be replaced with the full path of the current
    working directory. "{ds}" and "{refds}" will provide instances of the dataset currently opreplaced with the full
    path
    of the
    dataset that run is invoked on. "{tmpdir}" will be replaced with the full
    path of a temporary directory.
    << REFLOW ||
    """
    # TODO:     _examples_ = [], # see e.g. run

    _params_ = dict(
        cmd=Parameter(
            args=("cmd",),
            nargs=REMAINDER,
            metavar='COMMAND',
            doc="""command for execution. [CMD: A leading '--' can be used to
            disambiguate this command from the preceding options to DataLad.
            For --cmd-type exec or eval only a single
            command argument (Python code) is supported. CMD]
            [PY: For `cmd_type='exec'` or `cmd_type='eval'` (Python code) should
            be either a string or a list with only a single item. PY]
            """),
        cmd_type=Parameter(
            args=("--cmd-type",),
            constraints=EnsureChoice('external', 'exec', 'eval'),
            doc="""type of the command. `external`: to be run in a child process using dataset's runner;
            'exec': Python source code to execute using 'exec(), no value returned;
            'eval': Python source code to evaluate using 'eval()', return value is placed into 'result' field."""),
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
        # But not clear how to specify `None` from CLI if I default it to True
        fulfilled=fulfilled,
        recursive=recursion_flag,
        recursion_limit=recursion_limit,
        contains=contains,
        bottomup=Parameter(
            args=("--bottomup",),
            action="store_true",
            doc="""whether to report subdatasets in bottom-up order along
            each branch in the dataset tree, and not top-down."""),
        # Extra options
        # TODO: --diff  to provide `diff` record so any arbitrary  git reset --hard etc desire could be fulfilled
        # TODO: should we just introduce --lower-recursion-limit aka --mindepth of find?
        subdatasets_only=Parameter(
            args=("-s", "--subdatasets-only"),
            action="store_true",
            doc="""whether to exclude top level dataset.  It is implied if a non-empty
            `contains` is used"""),
        output_streams=Parameter(  # TODO  could be of use for `run` as well
            args=("--output-streams", "--o-s"),
            constraints=EnsureChoice('capture', 'pass-through'),
            doc="""whether to capture and return outputs from 'cmd' in the record ('stdout', 'stderr') or
            just 'pass-through' to the screen (and thus absent from returned record)."""),
        jobs=jobs_opt,
        # TODO: might want explicit option to either worry about 'safe_to_consume' setting for parallel
        # For now - always safe
    )

    @staticmethod
    @datasetmethod(name='foreach')
    @eval_results
    def __call__(
            cmd=None,
            cmd_type="external",
            dataset=None,
            fulfilled=None,
            recursive=False,
            recursion_limit=None,
            contains=None,
            bottomup=False,
            subdatasets_only=False,
            output_streams='capture',
            jobs=None
            ):
        if not cmd:
            raise InsufficientArgumentsError("No command given")
        python = cmd_type in _PYTHON_CMDS
        if python:
            # yoh decided to avoid unnecessary complication/inhomogeneity with support
            # of multiple Python commands for now; and also allow for a single string command
            # in Python interface
            if isinstance(cmd, (list, tuple)):
                if len(cmd) > 1:
                    raise ValueError(f"Please provide a single Python expression. Got {len(cmd)}: {cmd!r}")
                cmd = cmd[0]
            if not isinstance(cmd, str):
                raise ValueError(f"Please provide a single Python expression. Got {cmd!r}")
        else:
            protocol = NoCapture if output_streams == 'pass-through' else StdOutErrCapture

        refds = require_dataset(
            dataset, check_installed=True, purpose='foreach execution')
        pwd = getpwd()  # Note: 'run' has some more elaborate logic for this

        #
        # Producer -- datasets to act on
        #
        subdatasets_it = refds.subdatasets(
            fulfilled=fulfilled,
            recursive=recursive, recursion_limit=recursion_limit,
            contains=contains,
            bottomup=bottomup,
            result_xfm='paths'
        )

        if subdatasets_only or contains:
            datasets_it = subdatasets_it
        else:
            if bottomup:
                datasets_it = chain(subdatasets_it, [refds.path])
            else:
                datasets_it = chain([refds.path], subdatasets_it)

        #
        # Consumer - one for all cmd_type's
        #
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
                # pass actual instances so .format could access attributes even for external commands
                ds=ds,  # if python else ds.path,
                dspath=ds.path,  # just for consistency with `run`
                refds=refds,  # if python else refds.path,
                # Check if the command contains "tmpdir" to avoid creating an
                # unnecessary temporary directory in most but not all cases.
                # Note: different from 'run' - not wrapping match within {} and doing str
                tmpdir=mkdtemp(prefix="datalad-run-") if "tmpdir" in str(cmd) else "")
            try:
                if python:
                    python_cmd = _PYTHON_CMDS[cmd_type]
                    with chpwd(ds.path):
                        if output_streams == 'pass-through':
                            res = python_cmd(cmd, placeholders)
                            out = {}
                        elif output_streams == 'capture':
                            with swallow_outputs() as cmo:
                                res = python_cmd(cmd, placeholders)
                                out = {
                                    'stdout': cmo.out,
                                    'stderr': cmo.err,
                                }
                        else:
                            raise RuntimeError(output_streams)
                        if cmd_type == 'eval':
                            status_rec['result'] = res
                        else:
                            assert res is None
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
                if output_streams == 'capture':
                    status_rec.update(out)
                    # provide some feedback to user in default rendering
                    if any(out.values()):
                        status_rec['message'] = shortened_repr(out, 100)
                status_rec['status'] = 'ok'
                yield status_rec
            except Exception as exc:
                # get a better version with exception handling redoing the whole
                # status dict from scratch
                yield get_status_dict(
                    'foreach',
                    ds=ds,
                    path=ds.path,
                    command=cmd,
                    exception=exc,
                    status='error',
                    message=str(exc))

        if output_streams == 'pass-through':
            pc_class = ProducerConsumer
            pc_kw = {}
        else:
            pc_class = ProducerConsumerProgressLog
            pc_kw = dict(lgr=lgr, label="foreach", unit="datasets")

        yield from pc_class(
            producer=datasets_it,
            consumer=run_cmd,
            # probably not needed
            # It is ok to start with subdatasets since top dataset already exists
            safe_to_consume=no_subds_in_futures if bottomup else no_parentds_in_futures,
            # or vise versa
            jobs=jobs,
            **pc_kw
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
