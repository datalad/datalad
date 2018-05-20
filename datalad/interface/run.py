# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Run arbitrary commands and track how they modify a dataset"""

__docformat__ = 'restructuredtext'


import logging
import json

from argparse import REMAINDER
from glob import glob
from os.path import join as opj
from os.path import curdir
from os.path import isdir
from os.path import normpath
from os.path import relpath

from datalad.interface.base import Interface
from datalad.interface.utils import eval_results
from datalad.interface.base import build_doc
from datalad.interface.results import get_status_dict
from datalad.interface.common_opts import save_message_opt

from datalad.support.annexrepo import AnnexRepo
from datalad.support.constraints import EnsureChoice
from datalad.support.constraints import EnsureNone
from datalad.support.exceptions import CommandError
from datalad.support.param import Parameter

from datalad.distribution.add import Add
from datalad.distribution.get import Get
from datalad.distribution.remove import Remove
from datalad.distribution.dataset import require_dataset
from datalad.distribution.dataset import EnsureDataset
from datalad.distribution.dataset import datasetmethod
from datalad.interface.unlock import Unlock

from datalad.utils import chpwd
from datalad.utils import get_dataset_root
from datalad.utils import getpwd
from datalad.utils import partition

lgr = logging.getLogger('datalad.interface.run')


def _format_cmd_shorty(cmd):
    """Get short string representation from a cmd argument list"""
    cmd_shorty = (' '.join(cmd) if isinstance(cmd, list) else cmd)
    cmd_shorty = '{}{}'.format(
        cmd_shorty[:40],
        '...' if len(cmd_shorty) > 40 else '')
    return cmd_shorty


@build_doc
class Run(Interface):
    """Run an arbitrary shell command and record its impact on a dataset.

    It is recommended to craft the command such that it can run in the root
    directory of the dataset that the command will be recorded in. However,
    as long as the command is executed somewhere underneath the dataset root,
    the exact location will be recorded relative to the dataset root.

    If the executed command did not alter the dataset in any way, no record of
    the command execution is made.

    If the given command errors, a `CommandError` exception with the same exit
    code will be raised, and no modifications will be saved.
    """
    _params_ = dict(
        cmd=Parameter(
            args=("cmd",),
            nargs=REMAINDER,
            metavar='COMMAND',
            doc="command for execution"),
        dataset=Parameter(
            args=("-d", "--dataset"),
            doc="""specify the dataset to record the command results in.
            An attempt is made to identify the dataset based on the current
            working directory. If a dataset is given, the command will be
            executed in the root directory of this dataset.""",
            constraints=EnsureDataset() | EnsureNone()),
        inputs=Parameter(
            args=("--input",),
            dest="inputs",
            metavar=("PATH"),
            action='append',
            doc="""A dependency for the run. Before running the command, the
            content of this file will be retrieved. A value of "." means "run
            :command:`datalad get .`". The value can also be a glob. [CMD: This
            option can be given more than once. CMD]"""),
        outputs=Parameter(
            args=("--output",),
            dest="outputs",
            metavar=("PATH"),
            action='append',
            doc="""Prepare this file to be an output file of the command. A
            value of "." means "run :command:`datalad unlock .`" (and will fail
            if some content isn't present). For any other value, if the content
            of this file is present, unlock the file. Otherwise, remove it. The
            value can also be a glob. [CMD: This option can be given more than
            once. CMD]"""),
        expand=Parameter(
            args=("--expand",),
            metavar=("WHICH"),
            doc="""Expand globs when storing inputs and/or outputs in the
            commit message.""",
            constraints=EnsureNone() | EnsureChoice("inputs", "outputs", "both")),
        message=save_message_opt,
        rerun=Parameter(
            args=('--rerun',),
            action='store_true',
            doc="""re-run the command recorded in the last saved change (if any).
            Note: This option is deprecated since version 0.9.2 and
            will be removed in a later release. Use `datalad rerun`
            instead."""),
    )

    @staticmethod
    @datasetmethod(name='run')
    @eval_results
    def __call__(
            cmd=None,
            dataset=None,
            inputs=None,
            outputs=None,
            expand=None,
            message=None,
            rerun=False):
        if rerun:
            if cmd:
                lgr.warning("Ignoring provided command in --rerun mode")
            lgr.warning("The --rerun option is deprecated since version 0.9.2. "
                        "Use `datalad rerun` instead.")
            from datalad.interface.rerun import Rerun
            for r in Rerun.__call__(dataset=dataset, message=message):
                yield r
        else:
            if cmd:
                for r in run_command(cmd, dataset=dataset,
                                     inputs=inputs, outputs=outputs,
                                     expand=expand,
                                     message=message):
                    yield r
            else:
                lgr.warning("No command given")


def _expand_globs(patterns, pwd, warn=True):
    patterns, dots = partition(patterns, lambda i: i.strip() == ".")
    expanded = ["."] if list(dots) else []
    with chpwd(pwd):
        for pattern in patterns:
            hits = glob(pattern)
            if hits:
                expanded.extend(hits)
            elif warn:
                lgr.warning("No matching files found for %s", pattern)
    return expanded


def get_command_pwds(dataset):
    """Return the directory for the command.

    Parameters
    ----------
    dataset : Dataset

    Returns
    -------
    A tuple, where the first item is the absolute path of the pwd and the
    second is the pwd relative to the dataset's path.
    """
    if dataset:
        pwd = dataset.path
        rel_pwd = curdir
    else:
        # act on the whole dataset if nothing else was specified
        dataset = get_dataset_root(curdir)
        # Follow our generic semantic that if dataset is specified,
        # paths are relative to it, if not -- relative to pwd
        pwd = getpwd()
        if dataset:
            rel_pwd = relpath(pwd, dataset)
        else:
            rel_pwd = pwd  # and leave handling on deciding either we
                           # deal with it or crash to checks below
    return pwd, rel_pwd

# This helper function is used to add the rerun_info argument.
def run_command(cmd, dataset=None, inputs=None, outputs=None, expand=None,
                message=None, rerun_info=None):
    rel_pwd = rerun_info.get('pwd') if rerun_info else None
    if rel_pwd and dataset:
        # recording is relative to the dataset
        pwd = normpath(opj(dataset.path, rel_pwd))
        rel_pwd = relpath(pwd, dataset.path)
    else:
        pwd, rel_pwd = get_command_pwds(dataset)

    ds = require_dataset(
        dataset, check_installed=True,
        purpose='tracking outcomes of a command')

    # not needed ATM
    #refds_path = ds.path

    # delayed imports
    from datalad.cmd import Runner

    lgr.debug('tracking command output underneath %s', ds)
    if not rerun_info and ds.repo.dirty:  # Rerun already takes care of this.
        yield get_status_dict(
            'run',
            ds=ds,
            status='impossible',
            message=('unsaved modifications present, '
                     'cannot detect changes by command'))
        return

    if inputs is None:
        inputs = []
    elif inputs:
        inputs_expanded = _expand_globs(inputs, pwd)
        if inputs_expanded:
            for res in ds.get(inputs_expanded, on_failure="ignore"):
                yield res
            if expand in ["inputs", "both"]:
                inputs = inputs_expanded

    if outputs is None:
        outputs = []
    elif outputs:
        outputs_expanded = _expand_globs(outputs, pwd, warn=not rerun_info)
        if outputs_expanded:
            for res in ds.unlock(outputs_expanded, on_failure="ignore"):
                if res["status"] == "impossible":
                    if "no content" in res["message"]:
                        for rem_res in ds.remove(res["path"],
                                                 check=False, save=False):
                            yield rem_res
                        continue
                    elif "path does not exist" in res["message"]:
                        continue
                yield res
            if expand in ["outputs", "both"]:
                outputs = outputs_expanded

    # anticipate quoted compound shell commands
    cmd = cmd[0] if isinstance(cmd, list) and len(cmd) == 1 else cmd

    # TODO do our best to guess which files to unlock based on the command string
    #      in many cases this will be impossible (but see rerun). however,
    #      generating new data (common case) will be just fine already

    # we have a clean dataset, let's run things
    exc = None
    cmd_exitcode = None
    runner = Runner(cwd=pwd)
    try:
        lgr.info("== Command start (output follows) =====")
        runner.run(
            cmd,
            # immediate output
            log_online=True,
            # not yet sure what we should do with the command output
            # IMHO `run` itself should be very silent and let the command talk
            log_stdout=False,
            log_stderr=False,
            expect_stderr=True,
            expect_fail=True,
            # TODO stdin
        )
    except CommandError as e:
        # strip our own info from the exception. The original command output
        # went to stdout/err -- we just have to exitcode in the same way
        exc = e
        cmd_exitcode = e.code

        if rerun_info and rerun_info.get("exit", 0) != cmd_exitcode:
            # we failed in a different way during a rerun.  This can easily
            # happen if we try to alter a locked file
            #
            # TODO add the ability to `git reset --hard` the dataset tree on failure
            # we know that we started clean, so we could easily go back, needs gh-1424
            # to be able to do it recursively
            raise exc

    lgr.info("== Command exit (modification check follows) =====")

    # amend commit message with `run` info:
    # - pwd if inside the dataset
    # - the command itself
    # - exit code of the command
    run_info = {
        'cmd': cmd,
        'exit': cmd_exitcode if cmd_exitcode is not None else 0,
        'chain': rerun_info["chain"] if rerun_info else [],
        'inputs': inputs,
        # Get outputs from the rerun_info because rerun adds new/modified files
        # to the outputs argument.
        'outputs': rerun_info["outputs"] if rerun_info else outputs
    }
    if rel_pwd is not None:
        # only when inside the dataset to not leak information
        run_info['pwd'] = rel_pwd

    # compose commit message
    msg = '[DATALAD RUNCMD] {}\n\n=== Do not change lines below ===\n{}\n^^^ Do not change lines above ^^^'.format(
        message if message is not None else _format_cmd_shorty(cmd),
        json.dumps(run_info, indent=1), sort_keys=True, ensure_ascii=False, encoding='utf-8')

    if not rerun_info and cmd_exitcode:
        msg_path = opj(relpath(ds.repo.repo.git_dir), "COMMIT_EDITMSG")
        with open(msg_path, "w") as ofh:
            ofh.write(msg)
        lgr.info("The command had a non-zero exit code. "
                 "If this is expected, you can save the changes with "
                 "'datalad save -r -F%s .'",
                 msg_path)
        raise exc
    else:
        for r in ds.add('.', recursive=True, message=msg):
            yield r
