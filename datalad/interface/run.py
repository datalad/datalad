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
from os.path import join as opj
from os.path import curdir
from os.path import pardir
from os.path import relpath

from datalad.cmd import Runner

from datalad.interface.base import Interface
from datalad.interface.utils import eval_results
from datalad.interface.base import build_doc
from datalad.interface.results import get_status_dict
from datalad.interface.common_opts import save_message_opt

from datalad.support.constraints import EnsureNone
from datalad.support.constraints import EnsureStr
from datalad.support.constraints import EnsureChoice
from datalad.support.exceptions import CommandError
from datalad.support.exceptions import InsufficientArgumentsError
from datalad.support.param import Parameter

from datalad.distribution.dataset import Dataset
from datalad.distribution.dataset import require_dataset
from datalad.distribution.dataset import EnsureDataset
from datalad.distribution.dataset import datasetmethod

from datalad.utils import get_dataset_root
from datalad.utils import getpwd
from datalad.tests.utils import ok_clean_git

lgr = logging.getLogger('datalad.interface.run')


@build_doc
class Run(Interface):
    """Run and explain

    If the executed command did not alter the dataset in any way, no record of
    the command execution is made.

    If the given command errors, a `CommandError` exception with the same exit
    code will be raised.

    The executed command, the process working directory (PWD; if it is inside
    the given dataset), and the command's exit code will be recorded in the
    commit message.
    """
    _params_ = dict(
        cmd=Parameter(
            args=("cmd",),
            nargs=REMAINDER,
            metavar='SHELL COMMAND',
            doc="command for execution"),
        dataset=Parameter(
            args=("-d", "--dataset"),
            doc="""specify the dataset to query.  If
            no dataset is given, an attempt is made to identify the dataset
            based on the input and/or the current working directory""",
            constraints=EnsureDataset() | EnsureNone()),
        message=save_message_opt,
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
            message=None):
        if not dataset:
            # act on the whole dataset if nothing else was specified
            dataset = get_dataset_root(curdir)
        ds = require_dataset(
            dataset, check_installed=True,
            purpose='tracking outcomes of a command')
        rel_pwd = relpath(getpwd(), start=ds.path)
        if rel_pwd.startswith(pardir):
            lgr.warning('Process working directory not inside the dataset, command run may not be reproducible.')
            rel_pwd = None
        # not needed ATM
        #refds_path = ds.path
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

        if not cmd:
            # TODO here we would need to recover a cmd when a rerun is attempted
            return

        # anticipate quoted compound shell commands
        cmd = cmd[0] if isinstance(cmd, list) and len(cmd) == 1 else cmd

        # TODO do our best to guess which files to unlock based on the command string
        #      in many cases this will be impossible (but see --rerun). however,
        #      generating new data (common case) will be just fine already

        # we have a clean dataset, let's run things
        cmd_exitcode = None
        runner = Runner()
        try:
            print(cmd)
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
            # TODO add the ability to `git reset --hard` the dataset tree on failure
            # we know that we started clean, so we could easily go back
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
            json.dumps(run_info, indent=1))

        for r in ds.add('.', recursive=True, message=msg):
            yield r

        if cmd_exitcode:
            # finally raise due to the original command error
            raise CommandError(code=cmd_exitcode)
