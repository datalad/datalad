# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Run log arbitrary comands and track how they modify a dataset"""

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
        # TODO
        # --list-commands
        #   go through the history and report any recorded command. this info
        #   could be used to unlock the associated output files for a rerun
        # --rerun #
        #   rerun command # from the list of recorded commands using the info/cmd
        #   on record
        # --message
        #   prepend default message and replace default short summary
    )

    # TODO running a command outside a dataset should be supported, but it will prevent
    # a reliable rerun, and we do not want to record absolute CWD paths...

    @staticmethod
    @datasetmethod(name='run')
    @eval_results
    def __call__(
            # it is optional, because `rerun` can get a recorded one
            cmd=None,
            dataset=None):
        if not dataset:
            # act on the whole dataset if nothing else was specified
            dataset = get_dataset_root(curdir)
        ds = require_dataset(
            dataset, check_installed=True,
            purpose='tracking outcomes of a command')
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
        lgr.info("== Command exit (modification check follows) =====")

        # TODO what if a command did not alter the dataset? Record nothing? Empty commit?

        # TODO ammend commit message with `run` info:
        # - cwd if inside the dataset
        # - the command itself
        run_info = {
            'command': cmd,
        }
        rel_pwd = relpath(getpwd(), start=ds.path)
        if not rel_pwd.startswith(pardir):
            # only when inside the dataset to not leak information
            run_info['pwd'] = rel_pwd

        # compose commit message
        cmd_shorty = (' '.join(cmd) if isinstance(cmd, list) else cmd)
        cmd_shorty = '{}{}'.format(
            cmd_shorty[:40],
            '...' if len(cmd_shorty) > 40 else '')
        msg = '[DATALAD RUNCMD] {}\n\n{}'.format(
            cmd_shorty,
            # YAML might be a better choice...
            json.dumps(run_info, indent=1))

        #for r in ds.save(all_changes=True, recursive=True):
        for r in ds.add('.', recursive=True, message=msg):
            # TODO make `add` look for modifications like `save` to spare us the flood
            # of useless 'got nothing new here messages'
            if r.get('status', None) == 'notneeded':
                # the user didn't trigger this action, hence it makes very little sense
                # to raise awareness that something did not happen
                continue
            yield r

        if cmd_exitcode:
            # finally raise due to the original command error
            raise CommandError(code=cmd_exitcode)
