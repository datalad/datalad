# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Rerun commands recorded with `datalad run`"""

__docformat__ = 'restructuredtext'


import logging
from itertools import dropwhile
import json
import os
import re
import sys

from datalad.dochelpers import exc_str
from datalad.interface.base import Interface
from datalad.interface.utils import eval_results
from datalad.interface.base import build_doc
from datalad.interface.diff import Diff
from datalad.interface.unlock import Unlock
from datalad.interface.results import get_status_dict
from datalad.interface.run import run_command
from datalad.interface.run import _format_cmd_shorty

from datalad.support.constraints import EnsureNone, EnsureStr
from datalad.support.gitrepo import GitCommandError
from datalad.support.param import Parameter

from datalad.distribution.dataset import require_dataset
from datalad.distribution.dataset import EnsureDataset
from datalad.distribution.dataset import datasetmethod

lgr = logging.getLogger('datalad.interface.rerun')


@build_doc
class Rerun(Interface):
    """Re-execute previous `datalad run` commands.

    This will unlock any dataset content that is on record to have
    been modified by the command in the specified revision.  It will
    then re-execute the command in the recorded path (if it was inside
    the dataset). Afterwards, all modifications will be saved.

    Examples:

      Re-execute the command from the previous commit::

        % datalad rerun

      Re-execute any commands in the last five commits::

        % datalad rerun --since=HEAD~5

      Do the same as above, but re-execute the commands on top of
      HEAD~5 in a detached state::

        % datalad rerun --onto= --since=HEAD~5

      Re-execute all previous commands and compare the old and new
      results::

        % # on master branch
        % datalad rerun --branch=verify --since=
        % # now on verify branch
        % datalad diff --revision=master..
        % git log --oneline --left-right --cherry-pick master...

    .. note::
      Currently the "onto" feature only sets the working tree of the current
      dataset to a previous state. The working trees of any subdatasets remain
      unchanged.
    """
    _params_ = dict(
        revision=Parameter(
            args=("revision",),
            metavar="REVISION",
            nargs="?",
            doc="""rerun command(s) in `revision`. By default, the command from
            this commit will be executed, but [CMD: --since CMD][PY: `since`
            PY] can be used to construct a revision range.""",
            default="HEAD",
            constraints=EnsureStr()),
        since=Parameter(
            args=("--since",),
            doc="""If `since` is a commit-ish, the commands from all commits
            that are reachable from `revision` but not `since` will be
            re-executed (in other words, the commands in :command:`git log
            SINCE..REVISION`). If SINCE is an empty string, it is set to the
            parent of the first commit that contains a recorded command (i.e.,
            all commands in :command:`git log REVISION` will be
            re-executed).""",
            constraints=EnsureStr() | EnsureNone()),
        branch=Parameter(
            metavar="NAME",
            args=("-b", "--branch",),
            doc="create and checkout this branch before rerunning the commands.",
            constraints=EnsureStr() | EnsureNone()),
        onto=Parameter(
            metavar="base",
            args=("--onto",),
            doc="""start point for rerunning the commands. If not specified,
            commands are executed at HEAD. This option can be used to specify
            an alternative start point, which will be checked out with the
            branch name specified by [CMD: --branch CMD][PY: `branch` PY] or in
            a detached state otherwise. As a special case, an empty value for
            this option means to use the commit specified by [CMD: --since
            CMD][PY: `since` PY].""",
            constraints=EnsureStr() | EnsureNone()),
        message=Parameter(
            args=("-m", "--message",),
            metavar="MESSAGE",
            doc="""use MESSAGE for the reran commit rather than the
            recorded commit message.  In the case of a multi-commit
            rerun, all the reran commits will have this message.""",
            constraints=EnsureStr() | EnsureNone()),
        script=Parameter(
            args=("--script",),
            metavar="FILE",
            doc="""extract the commands into [CMD: FILE CMD][PY: this file PY]
            rather than rerunning.  Use - to write to stdout instead.""",
            constraints=EnsureStr() | EnsureNone()),
        dataset=Parameter(
            args=("-d", "--dataset"),
            doc="""specify the dataset from which to rerun a recorded
            command. If no dataset is given, an attempt is made to
            identify the dataset based on the current working
            directory. If a dataset is given, the command will be
            executed in the root directory of this dataset.""",
            constraints=EnsureDataset() | EnsureNone()),
        # TODO
        # --list-commands
        #   go through the history and report any recorded command. this info
        #   could be used to unlock the associated output files for a rerun
    )

    @staticmethod
    @datasetmethod(name='rerun')
    @eval_results
    def __call__(
            revision="HEAD",
            since=None,
            dataset=None,
            branch=None,
            message=None,
            onto=None,
            script=None):

        ds = require_dataset(
            dataset, check_installed=True,
            purpose='rerunning a command')

        lgr.debug('rerunning command output underneath %s', ds)

        if script is None and ds.repo.dirty:
            yield get_status_dict(
                'run',
                ds=ds,
                status='impossible',
                message=('unsaved modifications present, '
                         'cannot detect changes by command'))
            return

        err_info = get_status_dict('run', ds=ds)
        if not ds.repo.get_hexsha():
            yield dict(
                err_info, status='impossible',
                message='cannot rerun command, nothing recorded')
            return

        if branch and branch in ds.repo.get_branches():
            yield get_status_dict(
                "run", ds=ds, status="error",
                message="branch '{}' already exists".format(branch))
            return

        if not commit_exists(ds, revision + "^"):
            # Only a single commit is reachable from `revision`.  In
            # this case, --since has no effect on the range construction.
            revrange = revision
        elif since is None:
            revrange = "{rev}^..{rev}".format(rev=revision)
        elif since.strip() == "":
            revrange = revision
        else:
            revrange = "{}..{}".format(since, revision)

        if ds.repo.repo.git.rev_list("--merges", revrange, "--"):
            yield get_status_dict(
                "run", ds=ds, status="error",
                message="cannot rerun history with merge commits")
            return

        revs = [{"hexsha": hexsha,
                 "message": ds.repo.repo.git.show(
                     hexsha, "--format=%B", "--no-patch")}
                for hexsha in ds.repo.repo.git.rev_list(
                        "--reverse", revrange, "--").split()]

        for rev in revs:
            try:
                msg, info = get_run_info(rev["message"])
            except ValueError as exc:
                yield dict(err_info, status='error',
                           message="Error on {}'s message: {}".format(
                               rev["hexsha"], exc_str(exc)))
                return
            if info is not None:
                rev["run_info"] = info
                rev["run_message"] = msg

        if since is not None and since.strip() == "":
            # For --since='', drop any leading commits that don't have
            # a run command.
            revs = list(dropwhile(lambda r: "run_info" not in r, revs))

        if script:
            ofh = sys.stdout if script.strip() == "-" else open(script, "w")
            header = """\
#!/bin/sh
#
# This file was generated by running (the equivalent of)
#
#   datalad rerun --script={script}{since} {revision}
#
# in {ds}{path}\n"""
            ofh.write(header.format(
                script=script,
                since="" if since is None else " --since=" + since,
                revision=ds.repo.repo.git.rev_parse(revision),
                ds='dataset {} at '.format(ds.id) if ds.id else '',
                path=ds.path))

            for rev in revs:
                if "run_info" not in rev:
                    continue

                cmd = rev["run_info"]["cmd"]
                msg = rev["run_message"]
                if msg == _format_cmd_shorty(cmd):
                    msg = ''
                ofh.write(
                    "\n" + "".join("# " + ln
                                   for ln in msg.splitlines(True)) +
                    "\n")
                commit_descr = ds.repo.describe(rev['hexsha'])
                ofh.write('# (record: {})\n'.format(
                    commit_descr if commit_descr else rev['hexsha']))

                if isinstance(cmd, list):
                    cmd = " ".join(cmd)
                ofh.write(cmd + "\n")
            if ofh is not sys.stdout:
                ofh.close()
        else:
            if onto is not None and onto.strip() == "":
                # Special case: --onto='' is the value of --since.
                # Because we're currently aborting if the revision list
                # contains merges, we know that, regardless of if and how
                # --since is specified, the effective value for --since is
                # the parent of the first revision.
                onto = revs[0]["hexsha"] + "^"
                if not commit_exists(ds, onto):
                    # This is unlikely to happen in the wild because it
                    # means that the first commit is a datalad run commit.
                    # Just abort rather than trying to checkout on orphan
                    # branch or something like that.
                    yield get_status_dict(
                        "run", ds=ds, status="error",
                        message="Commit for --onto does not exist.")
                    return

            if branch or onto:
                start_point = onto or "HEAD"
                if branch:
                    checkout_options = ["-b", branch]
                else:
                    checkout_options = ["--detach"]
                ds.repo.checkout(start_point, options=checkout_options)

            for rev in revs:
                hexsha = rev["hexsha"]
                if "run_info" not in rev:
                    pick = False
                    try:
                        ds.repo.repo.git.merge_base("--is-ancestor",
                                                    hexsha, "HEAD")
                    except GitCommandError:
                        # Revision is NOT an ancestor of HEAD.
                        pick = True

                    shortrev = ds.repo.repo.git.rev_parse("--short", hexsha)
                    err_msg = "no command for {} found; {}".format(
                        shortrev,
                        "cherry picking" if pick else "skipping")
                    yield dict(err_info, status='ok', message=err_msg)

                    if pick:
                        ds.repo._git_custom_command(
                            None, ["git", "cherry-pick", hexsha],
                            check_fake_dates=True)
                    continue

                run_info = rev["run_info"]
                # Keep a "rerun" trail.
                if "chain" in run_info:
                    run_info["chain"].append(hexsha)
                else:
                    run_info["chain"] = [hexsha]

                # now we have to find out what was modified during the
                # last run, and enable re-modification ideally, we would
                # bring back the entire state of the tree with #1424, but
                # we limit ourself to file addition/not-in-place-modification
                # for now
                auto_outputs = (os.path.relpath(ap["path"], ds.path)
                                for ap in new_or_modified(ds, hexsha))
                outputs = run_info.get("outputs", [])
                auto_outputs = [p for p in auto_outputs if p not in outputs]

                for r in run_command(run_info['cmd'],
                                     dataset=ds,
                                     inputs=run_info.get("inputs", []),
                                     outputs=outputs + auto_outputs,
                                     message=message or rev["run_message"],
                                     rerun_info=run_info):
                    yield r


def get_run_info(message):
    """Extract run information from `message`

    Parameters
    ----------
    message : str
        A commit message.

    Returns
    -------
    A tuple with the command's message and a dict with run information. Both
    these values are None if `message` doesn't have a run command.

    Raises
    ------
    A ValueError if the information in `message` is invalid.
    """
    cmdrun_regex = r'\[DATALAD RUNCMD\] (.*)=== Do not change lines below ' \
                   r'===\n(.*)\n\^\^\^ Do not change lines above \^\^\^'
    runinfo = re.match(cmdrun_regex, message, re.MULTILINE | re.DOTALL)
    if not runinfo:
        return None, None

    rec_msg, runinfo = runinfo.groups()

    try:
        runinfo = json.loads(runinfo)
    except Exception as e:
        raise ValueError(
            'cannot rerun command, command specification is not valid JSON: '
            '%s' % exc_str(e)
        )
    if 'cmd' not in runinfo:
        raise ValueError("Looks like a run commit but does not have a command")
    return rec_msg.rstrip(), runinfo


def new_or_modified(dataset, revision="HEAD"):
    """Yield files that have been added or modified in `revision`.

    Parameters
    ----------
    dataset : Dataset
    revision : string, optional
        Commit-ish of interest.

    Returns
    -------
    Generator that yields AnnotatePaths instances
    """
    if commit_exists(dataset, revision + "^"):
        revrange = "{rev}^..{rev}".format(rev=revision)
    else:
        # No other commits are reachable from this revision.  Diff
        # with an empty tree instead.
        #             git hash-object -t tree /dev/null
        empty_tree = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
        revrange = "{}..{}".format(empty_tree, revision)
    diff = dataset.diff(recursive=True,
                        revision=revrange,
                        return_type='generator', result_renderer=None)
    for r in diff:
        if r.get('type') == 'file' and r.get('state') in ['added', 'modified']:
            r.pop('status', None)
            yield r


def commit_exists(dataset, commit):
    try:
        dataset.repo.repo.git.rev_parse("--verify", commit + "^{commit}")
    except:
        return False
    return True
