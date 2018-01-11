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
from os.path import relpath

from datalad.interface.base import Interface
from datalad.interface.utils import eval_results
from datalad.interface.base import build_doc
from datalad.interface.results import get_status_dict
from datalad.interface.common_opts import save_message_opt

from datalad.support.constraints import EnsureNone, EnsureStr
from datalad.support.exceptions import CommandError
from datalad.support.gitrepo import GitCommandError
from datalad.support.param import Parameter

from datalad.distribution.dataset import require_dataset
from datalad.distribution.dataset import EnsureDataset
from datalad.distribution.dataset import datasetmethod

from datalad.utils import get_dataset_root
from datalad.utils import getpwd

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
    command in the previous commit (or the revision specified by --revision).
    It will then re-execute the command in the recorded path (if it was inside
    the dataset). Afterwards, all modifications will be saved.

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
        revision=Parameter(
            args=("--revision",),
            doc="""re-run command(s) in this revision or range.  REVISION can be a commit-ish
            that resolves to a single commit whose command should be re-run.
            Otherwise, it is taken as a revision range.""",
            default="HEAD",
            constraints=EnsureStr()),
        branch=Parameter(
            args=("-b", "--branch",),
            doc="create and checkout this branch before rerunning the commands.",
            constraints=EnsureStr() | EnsureNone()),
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
            rerun=False,
            revision="HEAD",
            branch=None):

        if rerun and cmd:
            lgr.warning('Ignoring provided command in --rerun mode')
            cmd = None

        if not dataset:
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
        else:
            pwd = dataset.path
            rel_pwd = curdir

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

        try:
            # Transform a single-commit revision into a range.  Don't rely on
            # `".." in` for range check because it's fragile (e.g., REV^- is a
            # range).
            ds.repo.repo.git.rev_parse("--verify", "--quiet",
                                       revision + "^{commit}")
            revision = "{r}^..{r}".format(r=revision)
        except GitCommandError:
            # It's not a single commit.  Assume it's a range and return as is.
            pass

        revs = ds.repo.repo.git.rev_list("--reverse", revision).split()

        if rerun and branch:
            if branch in ds.repo.get_branches():
                yield get_status_dict(
                    'run',
                    ds=ds,
                    status='error',
                    message="branch '{}' already exists".format(branch))
                return
            ds.repo.checkout(revs[0], ["-b", branch])

        rec_msg = None
        for rev in revs:
            if rerun:
                # pull run info out of the revision's commit message
                err_info = get_status_dict('run', ds=ds)
                if not ds.repo.get_hexsha():
                    yield dict(
                        err_info, status='impossible',
                        message='cannot re-run command, nothing recorded')
                    return
                try:
                    rec_msg, runinfo = get_commit_runinfo(ds.repo, rev)
                except ValueError as exc:
                    yield dict(
                        err_info, status='error',
                        message=str(exc)
                    )
                    return
                if not runinfo:
                    if branch:
                        shortrev = ds.repo.repo.git.rev_parse("--short", rev)
                        yield dict(
                            err_info,
                            status='ok',
                            message=("no command for {} found; "
                                     "cherry picking".format(shortrev)))
                        ds.repo.repo.git.cherry_pick(rev)
                    else:
                        yield dict(
                            err_info,
                            status='impossible',
                            message=('cannot re-run command, last saved state '
                                     'does not look like a recorded command run'))
                    continue
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
                        revision="{r}^..{r}".format(r=rev),
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
                # not a rerun, use previously assigned pwd, rel_pwd depending
                # on either dataset was specified
                pass

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
                message or rec_msg or cmd_shorty,
                json.dumps(run_info, indent=1), sort_keys=True, ensure_ascii=False, encoding='utf-8')

            for r in ds.add('.', recursive=True, message=msg):
                yield r

            # TODO bring back when we can ignore a command failure
            #if cmd_exitcode:
            #    # finally raise due to the original command error
            #    raise CommandError(code=cmd_exitcode)


def get_commit_runinfo(repo, commit="HEAD"):
    """Return message and run record from a commit message

    If none found - returns None, None; if anything goes wrong - throws
    ValueError with the message describing the issue
    """
    commit_msg = repo.repo.git.show(commit, "--format=%s%n%n%b", "--no-patch")
    cmdrun_regex = r'\[DATALAD RUNCMD\] (.*)=== Do not change lines below ' \
                   r'===\n(.*)\n\^\^\^ Do not change lines above \^\^\^'
    runinfo = re.match(cmdrun_regex, commit_msg,
                       re.MULTILINE | re.DOTALL)
    if not runinfo:
        return None, None

    rec_msg, runinfo = runinfo.groups()

    try:
        runinfo = json.loads(runinfo)
    except Exception as e:
        raise ValueError(
            'cannot re-run command, command specification is not valid JSON: '
            '%s' % str(e)
        )
    if 'cmd' not in runinfo:
        raise ValueError(
            'cannot re-run command, command specification missing in '
            'recorded state'
        )
    return rec_msg, runinfo
