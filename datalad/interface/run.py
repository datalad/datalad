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
import re

from argparse import REMAINDER
from os.path import join as opj
from os.path import curdir
from os.path import normpath

from datalad.interface.base import Interface
from datalad.interface.utils import eval_results
from datalad.interface.base import build_doc
from datalad.interface.results import get_status_dict
from datalad.interface.common_opts import save_message_opt

from datalad.support.constraints import EnsureNone
from datalad.support.exceptions import CommandError
from datalad.support.param import Parameter

from datalad.distribution.dataset import require_dataset
from datalad.distribution.dataset import EnsureDataset
from datalad.distribution.dataset import datasetmethod

from datalad.utils import get_dataset_root

lgr = logging.getLogger('datalad.interface.run')


@build_doc
class Run(Interface):
    """Run an arbitrary command and record its impact on a dataset.

    It is recommended to craft the command such that it can run in the root
    directory of the dataset that the command will be recorded in. However,
    as long as the command is executed somewhere underneath the dataset root,
    the exact location will be recorded relative to the dataset root.

    Commands can be re-executed using the --rerun flag. This will unlock
    any dataset content that is on record to have been modified by the
    previous command run. It will then re-execute the command in the recorded
    path (if it was inside the dataset). Afterwards, all modifications will be
    saved.

    If the executed command did not alter the dataset in any way, no record of
    the command execution is made.

    If the given command errors, a `CommandError` exception with the same exit
    code will be raised, and no modifications will be saved.
    """
    _params_ = dict(
        cmd=Parameter(
            args=("cmd",),
            nargs=REMAINDER,
            metavar='SHELL COMMAND',
            doc="command for execution"),
        dataset=Parameter(
            args=("-d", "--dataset"),
            doc="""specify the dataset to record the command results in,
            or to rerun a recorded command from (see --rerun).  If
            no dataset is given, an attempt is made to identify the dataset
            based on the current working directory. If a dataset is given,
            the command will be executed in the root directory of this
            dataset.""",
            constraints=EnsureDataset() | EnsureNone()),
        message=save_message_opt,
        rerun=Parameter(
            args=('--rerun',),
            action='store_true',
            doc="""re-run the command recorded in the last saved change (if any).
            This will ignore any command given as an argument, and execute the
            recorded command call in the recorded working directory. The recorded
            changeset will be replaced by the outcome of the command re-run."""),
        # TODO
        # --list-commands
        #   go through the history and report any recorded command. this info
        #   could be used to unlock the associated output files for a rerun
        # --rerun #
        #   rerun command # from the list of recorded commands using the info/cmd
        #   on record
    )

    @staticmethod
    @datasetmethod(name='run')
    @eval_results
    def __call__(
            # it is optional, because `rerun` can get a recorded one
            cmd=None,
            dataset=None,
            message=None,
            rerun=False):
        if rerun and cmd:
            lgr.warning('Ignoring provided command in --rerun mode')
            cmd = None
        if not dataset:
            # act on the whole dataset if nothing else was specified
            dataset = get_dataset_root(curdir)
        ds = require_dataset(
            dataset, check_installed=True,
            purpose='tracking outcomes of a command')
        # not needed ATM
        #refds_path = ds.path

        # delayed imports
        from datalad.cmd import Runner
        from datalad.tests.utils import ok_clean_git

        lgr.debug('tracking command output underneath %s', ds)
        try:
            # base assumption is that the animal smells superb
            ok_clean_git(ds.path)
        except AssertionError:
            yield get_status_dict(
                'run',
                ds=ds,
                status='impossible',
                message='unsaved modifications present, cannot detect changes by command')
            return

        if not cmd and not rerun:
            # TODO here we would need to recover a cmd when a rerun is attempted
            return

        if rerun:
            # pull run info out of the last commit message
            err_info = get_status_dict('run', ds=ds)
            if not ds.repo.get_hexsha():
                yield dict(
                    err_info, status='impossible',
                    message='cannot re-run command, nothing recorded')
                return
            last_commit_msg = ds.repo.repo.head.commit.message
            cmdrun_regex = r'\[DATALAD RUNCMD\] (.*)=== Do not change lines below ===\n(.*)\n\^\^\^ Do not change lines above \^\^\^'
            runinfo = re.match(cmdrun_regex, last_commit_msg, re.MULTILINE | re.DOTALL)
            if not runinfo:
                yield dict(
                    err_info, status='impossible',
                    message='cannot re-run command, last saved state does not look like a recorded command run')
                return
            rec_msg, runinfo = runinfo.groups()
            if message is None:
                # re-use commit message, if nothing new was given
                message = rec_msg
            try:
                runinfo = json.loads(runinfo)
            except Exception as e:
                yield dict(
                    err_info, status='error',
                    message=('cannot re-run command, command specification is not valid JSON: %s', e.message))
                return
            if 'cmd' not in runinfo:
                yield dict(
                    err_info, status='error',
                    message='cannot re-run command, command specification missing in recorded state')
                return
            cmd = runinfo['cmd']
            rec_exitcode = runinfo.get('exit', 0)
            rel_pwd = runinfo.get('pwd', None)
            if rel_pwd:
                # recording is relative to the dataset
                pwd = normpath(opj(ds.path, rel_pwd))
            else:
                rel_pwd = None  # normalize, just in case
                pwd = None

            # now we have to find out what was modified during the last run, and enable re-modification
            # ideally, we would bring back the entire state of the tree with #1424, but we limit ourself
            # to file addition/not-in-place-modification for now
            to_unlock = []
            for r in ds.diff(
                    recursive=True,
                    revision='HEAD~1...HEAD',
                    return_type='generator',
                    result_renderer=None):
                if r.get('type', None) == 'file' and \
                        r.get('state', None) in ('added', 'modified'):
                    r.pop('status', None)
                    to_unlock.append(r)
            if to_unlock:
                for r in ds.unlock(to_unlock, return_type='generator', result_xfm=None):
                    yield r
        else:
            # not a rerun, figure out where we are running
            pwd = ds.path
            rel_pwd = curdir

        # anticipate quoted compound shell commands
        cmd = cmd[0] if isinstance(cmd, list) and len(cmd) == 1 else cmd

        # TODO do our best to guess which files to unlock based on the command string
        #      in many cases this will be impossible (but see --rerun). however,
        #      generating new data (common case) will be just fine already

        # we have a clean dataset, let's run things
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
            cmd_exitcode = e.code
            if not rerun or rec_exitcode != cmd_exitcode:
                # we failed during a fresh run, or in a different way during a rerun
                # the latter can easily happen if we try to alter a locked file
                #
                # let's fail here, the command could have had a typo or some
                # other undesirable condition. If we would `add` nevertheless,
                # we would need to rerun and aggregate annex content that we
                # likely don't want
                # TODO add switch to ignore failure (some commands are stupid)
                # TODO add the ability to `git reset --hard` the dataset tree on failure
                # we know that we started clean, so we could easily go back, needs gh-1424
                # to be able to do it recursively
                raise CommandError(code=cmd_exitcode)

        lgr.info("== Command exit (modification check follows) =====")

        # ammend commit message with `run` info:
        # - pwd if inside the dataset
        # - the command itself
        # - exit code of the command
        run_info = {
            'cmd': cmd,
            'exit': cmd_exitcode if cmd_exitcode is not None else 0,
        }
        if rel_pwd is not None:
            # only when inside the dataset to not leak information
            run_info['pwd'] = rel_pwd

        # compose commit message
        cmd_shorty = (' '.join(cmd) if isinstance(cmd, list) else cmd)
        cmd_shorty = '{}{}'.format(
            cmd_shorty[:40],
            '...' if len(cmd_shorty) > 40 else '')
        msg = '[DATALAD RUNCMD] {}\n\n=== Do not change lines below ===\n{}\n^^^ Do not change lines above ^^^'.format(
            message if message is not None else cmd_shorty,
            json.dumps(run_info, indent=1), sort_keys=True, ensure_ascii=False, encoding='utf-8')

        for r in ds.add('.', recursive=True, message=msg):
            yield r

        # TODO bring back when we can ignore a command failure
        #if cmd_exitcode:
        #    # finally raise due to the original command error
        #    raise CommandError(code=cmd_exitcode)
