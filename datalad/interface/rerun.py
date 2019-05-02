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
import os.path as op
import re
import sys

from datalad.dochelpers import exc_str
from datalad.interface.base import Interface
from datalad.interface.utils import eval_results
from datalad.interface.base import build_doc
from datalad.interface.results import get_status_dict
from datalad.interface.run import run_command
from datalad.interface.run import format_command
from datalad.interface.run import _format_cmd_shorty

from datalad.consts import PRE_INIT_COMMIT_SHA

from datalad.support.constraints import EnsureNone, EnsureStr
from datalad.support.param import Parameter
from datalad.support.json_py import load_stream

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

    *Report mode*

    || REFLOW >>
    When called with [CMD: --report CMD][PY: report=True PY], this command
    reports information about what would be re-executed as a series of records.
    There will be a record for each revision in the specified revision range.
    Each of these will have one of the following "rerun_action" values:
    << REFLOW ||

      - run: the revision has a recorded command that would be re-executed
      - skip: the revision does not have a recorded command and would be
        skipped
      - pick: the revision does not have a recorded command and would be cherry
        picked

    The decision to skip rather than cherry pick a revision is based on whether
    the revision would be reachable from HEAD at the time of execution.

    In addition, when a starting point other than HEAD is specified, there is a
    rerun_action value "checkout", in which case the record includes
    information about the revision the would be checked out before rerunning
    any commands.

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
            rather than rerunning. Use - to write to stdout instead. [CMD: This
            option implies --report. CMD]""",
            constraints=EnsureStr() | EnsureNone()),
        dataset=Parameter(
            args=("-d", "--dataset"),
            doc="""specify the dataset from which to rerun a recorded
            command. If no dataset is given, an attempt is made to
            identify the dataset based on the current working
            directory. If a dataset is given, the command will be
            executed in the root directory of this dataset.""",
            constraints=EnsureDataset() | EnsureNone()),
        report=Parameter(
            args=("--report",),
            action="store_true",
            doc="""Don't actually re-execute anything, just display what would
            be done. [CMD: Note: If you give this option, you most likely want
            to set --output-format to 'json' or 'json_pp'. CMD]"""),
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
            script=None,
            report=False):

        ds = require_dataset(
            dataset, check_installed=True,
            purpose='rerunning a command')

        lgr.debug('rerunning command output underneath %s', ds)

        if script is None and not report and ds.repo.dirty:
            yield get_status_dict(
                'run',
                ds=ds,
                status='impossible',
                message=('unsaved modifications present, '
                         'cannot detect changes by command'))
            return

        if not ds.repo.get_hexsha():
            yield get_status_dict(
                'run', ds=ds,
                status='impossible',
                message='cannot rerun command, nothing recorded')
            return

        if branch and branch in ds.repo.get_branches():
            yield get_status_dict(
                "run", ds=ds, status="error",
                message="branch '{}' already exists".format(branch))
            return

        if not ds.repo.commit_exists(revision + "^"):
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

        results = _rerun_as_results(ds, revrange, since, branch, onto, message)
        if script:
            handler = _get_script_handler(script, since, revision)
        elif report:
            handler = _report
        else:
            handler = _rerun

        for res in handler(ds, results):
            yield res


def _revs_as_results(dset, revs):
    for rev in revs:
        res = get_status_dict("run", ds=dset, commit=rev)
        full_msg = dset.repo.format_commit("%B", rev)
        try:
            msg, info = get_run_info(dset, full_msg)
        except ValueError as exc:
            # Recast the error so the message includes the revision.
            raise ValueError(
                "Error on {}'s message: {}".format(rev, exc_str(exc)))

        if info is not None:
            res["run_info"] = info
            res["run_message"] = msg
        yield dict(res, status="ok")


def _rerun_as_results(dset, revrange, since, branch, onto, message):
    """Represent the rerun as result records.

    In the standard case, the information in these results will be used to
    actually re-execute the commands.
    """
    revs = dset.repo.repo.git.rev_list("--reverse", revrange, "--").split()
    try:
        results = _revs_as_results(dset, revs)
    except ValueError as exc:
        yield get_status_dict("run", status="error", message=exc_str(exc))
        return

    if since is not None and since.strip() == "":
        # For --since='', drop any leading commits that don't have
        # a run command.
        results = list(dropwhile(lambda r: "run_info" not in r, results))
        if not results:
            yield get_status_dict(
                "run", status="impossible", ds=dset,
                message=("No run commits found in history of %s", revrange))
            return
    else:
        results = list(results)
        if not results:
            yield get_status_dict(
                "run", status="impossible", ds=dset,
                message=("No commits found in %s", revrange))
            return

    if onto is not None and onto.strip() == "":
        # Special case: --onto='' is the value of --since. Because we're
        # currently aborting if the revision list contains merges, we know
        # that, regardless of if and how --since is specified, the effective
        # value for --since is the parent of the first revision.
        onto = results[0]["commit"] + "^"

    if onto and not dset.repo.commit_exists(onto):
        # This happens either because the user specifies a value that doesn't
        # exists or the results first parent doesn't exist. The latter is
        # unlikely to happen in the wild because it means that the first commit
        # is a datalad run commit. Just abort rather than trying to checkout an
        # orphan branch or something like that.
        yield get_status_dict(
            "run", ds=dset, status="error",
            message=("Revision specified for --onto (%s) does not exist.",
                     onto))
        return

    start_point = onto or "HEAD"
    if branch or onto:
        yield get_status_dict(
            "run",
            ds=dset,
            commit=start_point,
            branch=branch,
            rerun_action="checkout",
            status="ok")

    def rev_is_ancestor(rev):
        return dset.repo.is_ancestor(rev, start_point)

    # We want to skip revs before the starting point and pick those after.
    to_pick = set(dropwhile(rev_is_ancestor, [r["commit"] for r in results]))

    def skip_or_pick(hexsha, result, msg):
        pick = hexsha in to_pick
        result["rerun_action"] = "pick" if pick else "skip"
        shortrev = dset.repo.get_hexsha(hexsha, short=True)
        result["message"] = (
            "%s %s; %s",
            shortrev, msg, "cherry picking" if pick else "skipping")

    for res in results:
        hexsha = res["commit"]
        if "run_info" in res:
            rerun_dsid = res["run_info"].get("dsid")
            if rerun_dsid is not None and rerun_dsid != dset.id:
                skip_or_pick(hexsha, res, "was ran from a different dataset")
                res["status"] = "impossible"
            else:
                res["rerun_action"] = "run"
                res["diff"] = diff_revision(dset, hexsha)
                # This is the overriding message, if any, passed to this rerun.
                res["rerun_message"] = message
        else:
            skip_or_pick(hexsha, res, "does not have a command")
        yield res


def _rerun(dset, results):
    for res in results:
        rerun_action = res.get("rerun_action")
        if not rerun_action:
            yield res
        elif rerun_action == "skip":
            yield res
        elif rerun_action == "checkout":
            if res.get("branch"):
                checkout_options = ["-b", res["branch"]]
            else:
                checkout_options = ["--detach"]
            dset.repo.checkout(res["commit"],
                               options=checkout_options)
        elif rerun_action == "pick":
            dset.repo.cherry_pick(res["commit"])
            yield res
        elif rerun_action == "run":
            hexsha = res["commit"]
            run_info = res["run_info"]

            # Keep a "rerun" trail.
            if "chain" in run_info:
                run_info["chain"].append(hexsha)
            else:
                run_info["chain"] = [hexsha]

            # now we have to find out what was modified during the last run,
            # and enable re-modification ideally, we would bring back the
            # entire state of the tree with #1424, but we limit ourself to file
            # addition/not-in-place-modification for now
            auto_outputs = (ap["path"] for ap in new_or_modified(res["diff"]))
            outputs = run_info.get("outputs", [])
            outputs_dir = op.join(dset.path, run_info["pwd"])
            auto_outputs = [p for p in auto_outputs
                            # run records outputs relative to the "pwd" field.
                            if op.relpath(p, outputs_dir) not in outputs]

            message = res["rerun_message"] or res["run_message"]
            for r in run_command(run_info['cmd'],
                                 dataset=dset,
                                 inputs=run_info.get("inputs", []),
                                 extra_inputs=run_info.get("extra_inputs", []),
                                 outputs=outputs,
                                 rerun_outputs=auto_outputs,
                                 message=message,
                                 rerun_info=run_info):
                yield r


def _report(dset, results):
    for res in results:
        if "run_info" in res:
            if res["status"] != "impossible":
                res["diff"] = list(res["diff"])
                # Add extra information that is useful in the report but not
                # needed for the rerun.
                out = dset.repo.format_commit("%an%x00%aI", res["commit"])
                res["author"], res["date"] = out.split("\0")
        yield res


def _get_script_handler(script, since, revision):
    ofh = sys.stdout if script.strip() == "-" else open(script, "w")

    def fn(dset, results):
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
            revision=dset.repo.get_hexsha(revision),
            ds='dataset {} at '.format(dset.id) if dset.id else '',
            path=dset.path))

        for res in results:
            if res["status"] != "ok":
                yield res
                return

            if "run_info" not in res:
                continue

            run_info = res["run_info"]
            cmd = run_info["cmd"]

            expanded_cmd = format_command(
                dset, cmd,
                **dict(run_info,
                       dspath=dset.path,
                       pwd=op.join(dset.path, run_info["pwd"])))

            msg = res["run_message"]
            if msg == _format_cmd_shorty(expanded_cmd):
                msg = ''

            ofh.write(
                "\n" + "".join("# " + ln
                               for ln in msg.splitlines(True)) +
                "\n")
            commit_descr = dset.repo.describe(res["commit"])
            ofh.write('# (record: {})\n'.format(
                commit_descr if commit_descr else res["commit"]))

            ofh.write(expanded_cmd + "\n")
        if ofh is not sys.stdout:
            ofh.close()

        if ofh is sys.stdout:
            yield None
        else:
            yield get_status_dict(
                "run", ds=dset, status="ok",
                path=script,
                message=("Script written to %s", script))

    return fn


def get_run_info(dset, message):
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
    if not isinstance(runinfo, (list, dict)):
        # this is a run record ID -> load the beast
        record_dir = dset.config.get(
            'datalad.run.record-directory',
            default=op.join('.datalad', 'runinfo'))
        record_path = op.join(dset.path, record_dir, runinfo)
        if not op.lexists(record_path):
            raise ValueError("Run record sidecar file not found: {}".format(record_path))
        # TODO `get` the file
        recs = load_stream(record_path, compressed=True)
        # TODO check if there is a record
        runinfo = next(recs)
    if 'cmd' not in runinfo:
        raise ValueError("Looks like a run commit but does not have a command")
    return rec_msg.rstrip(), runinfo


def diff_revision(dataset, revision="HEAD"):
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
    if dataset.repo.commit_exists(revision + "^"):
        fr = revision + "^"
    else:
        # No other commits are reachable from this revision.  Diff
        # with an empty tree instead.
        fr = PRE_INIT_COMMIT_SHA
    diff = dataset.diff(recursive=True,
                        fr=fr, to=revision,
                        return_type='generator', result_renderer=None)
    for r in diff:
        yield r


def new_or_modified(diff_results):
    """Filter diff result records to those for new or modified files.
    """
    for r in diff_results:
        if r.get('type') == 'file' and r.get('state') in ['added', 'modified']:
            r.pop('status', None)
            yield r
