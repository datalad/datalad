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


import inspect
import logging
import os.path as op
import sys
from argparse import REMAINDER
from itertools import chain
from tempfile import mkdtemp
from typing import Union

from datalad.cmd import (
    NoCapture,
    StdOutErrCapture,
)
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
    eval_results,
)
from datalad.interface.common_opts import (
    contains,
    dataset_state,
    jobs_opt,
    recursion_flag,
    recursion_limit,
)
from datalad.interface.results import get_status_dict
from datalad.support.constraints import (
    EnsureBool,
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
from datalad.utils import SequenceFormatter
from datalad.utils import chpwd as chpwd_cm
from datalad.utils import (
    getpwd,
    nothing_cm,
    shortened_repr,
    swallow_outputs,
)

lgr = logging.getLogger('datalad.local.foreach_dataset')


_PYTHON_CMDS = {
    'exec': exec,
    'eval': eval
}

# Centralize definition with delayed assignment for 'auto' for each case
_SAFE_TO_CONSUME_MAP = {
    'auto': lambda: 1/0,  # must be defined based on bottomup"
    'all-subds-done': no_subds_in_futures,
    'superds-done': no_parentds_in_futures,
    'always': None
}

@build_doc
class ForEachDataset(Interface):
    r"""Run a command or Python code on the dataset and/or each of its sub-datasets.

    This command provides a convenience for the cases were no dedicated DataLad command
    is provided to operate across the hierarchy of datasets. It is very similar to
    `git submodule foreach` command with the following major differences

    - by default (unless [CMD: --subdatasets-only CMD][PY: `subdatasets_only=True` PY]) it would
      include operation on the original dataset as well,
    - subdatasets could be traversed in bottom-up order,
    - can execute commands in parallel (see `jobs` option), but would account for the order,
      e.g. in bottom-up order command is executed in super-dataset only after it is executed
      in all subdatasets.

    Additional notes:

    - for execution of "external" commands we use the environment used to execute external
      git and git-annex commands.

    *Command format*

    || REFLOW >>
    [CMD: --cmd-type external CMD][PY: cmd_type='external' PY]: A few placeholders are
    supported in the command via Python format specification:
    << REFLOW ||


    - "{pwd}" will be replaced with the full path of the current working directory.
    - "{ds}" and "{refds}" will provide instances of the dataset currently
      operated on and the reference "context" dataset which was provided via ``dataset``
      argument.
    - "{tmpdir}" will be replaced with the full path of a temporary directory.
    """
    _examples_ = [
         dict(text="Aggressively  git clean  all datasets, running 5 parallel jobs",
              code_py="foreach_dataset(['git', 'clean', '-dfx'], recursive=True, jobs=5)",
              code_cmd="datalad foreach-dataset -r -J 5 git clean -dfx"),
     ]

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
            be either a string or a list with only a single item. If 'eval', the
            actual function can be passed, which will be provided all placeholders
            as keyword arguments. PY]
            """),
        cmd_type=Parameter(
            args=("--cmd-type",),
            constraints=EnsureChoice('auto', 'external', 'exec', 'eval'),
            doc="""type of the command. `external`: to be run in a child process using dataset's runner;
            'exec': Python source code to execute using 'exec(), no value returned;
            'eval': Python source code to evaluate using 'eval()', return value is placed into 'result' field.
            'auto': If used via Python API, and `cmd` is a Python function, it will use 'eval', and
            otherwise would assume 'external'."""),
        # Following options are taken from subdatasets
        dataset=Parameter(
            args=("-d", "--dataset"),
            doc="""specify the dataset to operate on.  If
            no dataset is given, an attempt is made to identify the dataset
            based on the input and/or the current working directory""",
            constraints=EnsureDataset() | EnsureNone()),
        state=dataset_state,
        recursive=recursion_flag,
        recursion_limit=recursion_limit,
        contains=contains,
        bottomup=Parameter(
            args=("--bottomup",),
            action="store_true",
            doc="""whether to report subdatasets in bottom-up order along
            each branch in the dataset tree, and not top-down."""),
        # Possible extra options to be introduced if use-case/demand comes
        # TODO: --diff  to provide `diff` record so any arbitrary  git reset --hard etc desire could be fulfilled
        # TODO: --lower-recursion-limit aka --mindepth of find to replace subdatasets-only.
        #  or may be recursion_limit could be made more sophisticated to be able to specify range
        subdatasets_only=Parameter(
            args=("-s", "--subdatasets-only"),
            action="store_true",
            doc="""whether to exclude top level dataset.  It is implied if a non-empty
            `contains` is used"""),
        output_streams=Parameter(
            args=("--output-streams", "--o-s"),
            constraints=EnsureChoice('capture', 'pass-through', 'relpath'),
            doc="""ways to handle outputs. 'capture' and return outputs from 'cmd' in the record ('stdout',
            'stderr'); 'pass-through' to the screen (and thus absent from returned record); prefix with 'relpath'
            captured output (similar to like grep does) and write to stdout and stderr. In 'relpath', relative path
            is relative to the top of the dataset if `dataset` is specified, and if not - relative to current
            directory."""),
        chpwd=Parameter(
            args=("--chpwd",),
            constraints=EnsureChoice('ds', 'pwd'),
            doc="""'ds' will change working directory to the top of the corresponding dataset. With 'pwd'
            no change of working directory will happen.
            Note that for Python commands, due to use of threads, we do not allow chdir=ds to be used
            with jobs > 1. Hint: use 'ds' and 'refds' objects' methods to execute commands in the context
            of those datasets.
            """),
        safe_to_consume=Parameter(
            args=("--safe-to-consume",),
            constraints=EnsureChoice(*_SAFE_TO_CONSUME_MAP),
            doc="""Important only in the case of parallel (jobs greater than 1) execution.
            'all-subds-done' instructs to not consider superdataset until command finished execution
            in all subdatasets (it is the value in case of 'auto' if traversal is bottomup).
            'superds-done' instructs to not process subdatasets until command finished in the super-dataset
            (it is the value in case of 'auto' in traversal is not bottom up, which is the default). With
            'always' there is no constraint on either to execute in sub or super dataset.
        """),
        jobs=jobs_opt,
    )

    @staticmethod
    @datasetmethod(name='foreach_dataset')
    @eval_results
    def __call__(
            cmd,
            *,
            cmd_type="auto",
            dataset=None,
            state='present',
            recursive=False,
            recursion_limit=None,
            contains=None,
            bottomup=False,
            subdatasets_only=False,
            output_streams='pass-through',
            chpwd='ds',  # as the most common case/scenario
            safe_to_consume='auto',
            jobs=None
            ):
        if not cmd:
            raise InsufficientArgumentsError("No command given")

        if safe_to_consume not in _SAFE_TO_CONSUME_MAP:
            raise ValueError(f"safe_to_consume - Unknown value {safe_to_consume!r}. "
                             f"Known are: {', '.join(_SAFE_TO_CONSUME_MAP)}")
        if safe_to_consume == 'auto':
            safe_to_consume_func = no_subds_in_futures if bottomup else no_parentds_in_futures
        else:
            safe_to_consume_func = _SAFE_TO_CONSUME_MAP[safe_to_consume]

        if cmd_type == 'auto':
            cmd_type = 'eval' if _is_callable(cmd) else 'external'

        python = cmd_type in _PYTHON_CMDS

        if python:
            if _is_callable(cmd):
                if cmd_type != 'eval':
                    raise ValueError(f"Can invoke provided function only in 'eval' mode. {cmd_type!r} was provided")
            else:
                # yoh decided to avoid unnecessary complication/inhomogeneity with support
                # of multiple Python commands for now; and also allow for a single string command
                # in Python interface
                if isinstance(cmd, (list, tuple)):
                    if len(cmd) > 1:
                        raise ValueError(f"Please provide a single Python expression. Got {len(cmd)}: {cmd!r}")
                    cmd = cmd[0]

                if not isinstance(cmd, str):
                    raise ValueError(f"Please provide a single Python expression or a function. Got {cmd!r}")
        else:
            if _is_callable(cmd):
                raise ValueError(f"cmd_type={cmd_type} but a function {cmd} was provided")
            protocol = NoCapture if output_streams == 'pass-through' else StdOutErrCapture

        refds = require_dataset(
            dataset, check_installed=True, purpose='foreach-dataset execution')
        pwd = getpwd()  # Note: 'run' has some more elaborate logic for this

        #
        # Producer -- datasets to act on
        #
        subdatasets_it = refds.subdatasets(
            state=state,
            recursive=recursive, recursion_limit=recursion_limit,
            contains=contains,
            bottomup=bottomup,
            result_xfm='paths',
            result_renderer='disabled',
            return_type='generator',
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
                'foreach-dataset',
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
                    if isinstance(cmd, str):
                        cmd_f, cmd_a, cmd_kw = _PYTHON_CMDS[cmd_type], (cmd, placeholders), {}
                    else:
                        assert _is_callable(cmd)
                        # all placeholders are passed as kwargs to the function
                        cmd_f, cmd_a, cmd_kw = cmd, [], placeholders

                    cm = chpwd_cm(ds.path) if chpwd == 'ds' else nothing_cm()
                    with cm:
                        if output_streams == 'pass-through':
                            res = cmd_f(*cmd_a, **cmd_kw)
                            out = {}
                        elif output_streams in ('capture', 'relpath'):
                            with swallow_outputs() as cmo:
                                res = cmd_f(*cmd_a, **cmd_kw)
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
                    out = ds.repo._git_runner.run(
                        cmd_expanded,
                        cwd=ds.path if chpwd == 'ds' else pwd,
                        protocol=protocol)
                if output_streams in ('capture', 'relpath'):
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
                    'foreach-dataset',
                    ds=ds,
                    path=ds.path,
                    command=cmd,
                    exception=exc,
                    status='error',
                    message=str(exc)
                )

        if output_streams == 'pass-through':
            pc_class = ProducerConsumer
            pc_kw = {}
        else:
            pc_class = ProducerConsumerProgressLog
            pc_kw = dict(lgr=lgr, label="foreach-dataset", unit="datasets")

        if python:
            effective_jobs = pc_class.get_effective_jobs(jobs)
            if effective_jobs > 1:
                warning = ""
                if chpwd == 'ds':
                    warning += \
                        "Execution of Python commands in parallel threads while changing directory " \
                        "is not thread-safe. "
                if output_streams in ('capture', 'relpath'):
                    warning += \
                        "Execution of Python commands in parallel while capturing output is not possible."
                if warning:
                    lgr.warning("Got jobs=%d. %s We will execute without parallelization", jobs, warning)
                    jobs = 0  # no threading even between producer/consumer

        yield from pc_class(
            producer=datasets_it,
            consumer=run_cmd,
            # probably not needed
            # It is ok to start with subdatasets since top dataset already exists
            safe_to_consume=safe_to_consume_func,
            # or vice versa
            jobs=jobs,
            **pc_kw
        )

    @staticmethod
    def custom_result_renderer(res, **kwargs):
        from datalad.interface.utils import generic_result_renderer
        if kwargs.get('output_streams') == 'relpath':
            from datalad.log import no_progress
            with no_progress():
                ds: Union[str, Dataset] = kwargs.get('dataset')
                if ds:
                    if not isinstance(ds, Dataset):
                        ds = Dataset(ds)  # so all ///, ^ etc get treated
                    refpath = ds.path
                else:
                    refpath = getpwd()
                for k in ('stdout', 'stderr'):
                    v = res.get(k)
                    if v:
                        path = res.get('path')
                        relpath = op.relpath(path, refpath) if path else ''
                        if relpath == op.curdir:
                            relpath = ''
                        if relpath and not relpath.endswith(op.sep):
                            relpath += op.sep
                        out = getattr(sys, k)
                        for l in v.splitlines():
                            out.write(f"{relpath}{l}\n")
        else:
            generic_result_renderer(res)

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


def _is_callable(f):
    return inspect.isfunction(f) or inspect.isbuiltin(f)
