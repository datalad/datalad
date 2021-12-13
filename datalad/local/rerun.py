# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Rerun commands recorded with `datalad run`"""

__docformat__ = 'restructuredtext'


import json
import logging
import os.path as op
import re
import sys
from copy import copy
from functools import partial
from itertools import dropwhile

from datalad.consts import PRE_INIT_COMMIT_SHA
from datalad.core.local.run import (
    _format_cmd_shorty,
    assume_ready_opt,
    format_command,
    run_command,
)
from datalad.distribution.dataset import (
    EnsureDataset,
    datasetmethod,
    require_dataset,
)
from datalad.interface.base import (
    Interface,
    build_doc,
)
from datalad.interface.results import get_status_dict
from datalad.interface.utils import eval_results
from datalad.interface.common_opts import jobs_opt

from datalad.support.constraints import (
    EnsureNone,
    EnsureStr,
)
from datalad.support.exceptions import CapturedException
from datalad.support.json_py import load_stream
from datalad.support.param import Parameter

lgr = logging.getLogger('datalad.local.rerun')

rerun_assume_ready_opt = copy(assume_ready_opt)
rerun_assume_ready_opt._doc += """
Note that this option also affects any additional outputs that are
automatically inferred based on inspecting changed files in the run commit."""


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
      - skip-or-pick: the revision does not have a recorded command and would
        be either skipped or cherry picked
      - merge: the revision is a merge commit and a corresponding merge would
        be made

    The decision to skip rather than cherry pick a revision is based on whether
    the revision would be reachable from HEAD at the time of execution.

    In addition, when a starting point other than HEAD is specified, there is a
    rerun_action value "checkout", in which case the record includes
    information about the revision the would be checked out before rerunning
    any commands.

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
            PY] can be used to construct a revision range. The default value is
            like "HEAD" but resolves to the main branch when on an adjusted
            branch.""",
            default=None,
            constraints=EnsureStr() | EnsureNone()),
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
            this option means the parent of the first run commit in the
            specified revision list.""",
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
        assume_ready=rerun_assume_ready_opt,
        explicit=Parameter(
            args=("--explicit",),
            action="store_true",
            doc="""Consider the specification of inputs and outputs in the run
            record to be explicit. Don't warn if the repository is dirty, and
            only save modifications to the outputs from the original record.
            Note that when several run commits are specified, this applies to
            every one. Care should also be taken when using [CMD: --onto
            CMD][PY: `onto` PY] because checking out a new HEAD can easily fail
            when the working tree has modifications."""),
        jobs=jobs_opt
    )

    _examples_ = [
        dict(text="Re-execute the command from the previous commit",
             code_py="rerun()",
             code_cmd="datalad rerun"),
        dict(text="Re-execute any commands in the last five commits",
             code_py="rerun(since='HEAD~5')",
             code_cmd="datalad rerun --since=HEAD~5"),
        dict(text="Do the same as above, but re-execute the commands on top of "
                  "HEAD~5 in a detached state",
             code_py="rerun(onto='', since='HEAD~5')",
             code_cmd="datalad rerun --onto= --since=HEAD~5"),
        dict(text="Re-execute all previous commands and compare the old and "
                  "new results",
             code_cmd="""% # on master branch
                % datalad rerun --branch=verify --since=
                % # now on verify branch
                % datalad diff --revision=master..
                % git log --oneline --left-right --cherry-pick master..."""),
    ]


    @staticmethod
    @datasetmethod(name='rerun')
    @eval_results
    def __call__(
            revision=None,
            *,
            since=None,
            dataset=None,
            branch=None,
            message=None,
            onto=None,
            script=None,
            report=False,
            assume_ready=None,
            explicit=False,
            jobs=None):

        ds = require_dataset(
            dataset, check_installed=True,
            purpose='rerun a command')
        ds_repo = ds.repo

        lgr.debug('rerunning command output underneath %s', ds)

        if script is None and not (report or explicit) and ds_repo.dirty:
            yield get_status_dict(
                'run',
                ds=ds,
                status='impossible',
                message=(
                    'clean dataset required to detect changes from command; '
                    'use `datalad status` to inspect unsaved changes'))
            return

        if not ds_repo.get_hexsha():
            yield get_status_dict(
                'run', ds=ds,
                status='impossible',
                message='cannot rerun command, nothing recorded')
            return

        # ATTN: Use get_corresponding_branch() rather than is_managed_branch()
        # for compatibility with a plain GitRepo.
        if (onto is not None or branch is not None) and \
           ds_repo.get_corresponding_branch():
            yield get_status_dict(
                "run", ds=ds, status="impossible",
                message=("--%s is incompatible with adjusted branch",
                         "branch" if onto is None else "onto"))
            return

        if branch and branch in ds_repo.get_branches():
            yield get_status_dict(
                "run", ds=ds, status="error",
                message="branch '{}' already exists".format(branch))
            return

        if revision is None:
            revision = ds_repo.get_corresponding_branch() or \
                ds_repo.get_active_branch() or "HEAD"

        if not ds_repo.commit_exists(revision + "^"):
            # Only a single commit is reachable from `revision`.  In
            # this case, --since has no effect on the range construction.
            revrange = revision
        elif since is None:
            revrange = "{rev}^..{rev}".format(rev=revision)
        elif since.strip() == "":
            revrange = revision
        else:
            revrange = "{}..{}".format(since, revision)

        results = _rerun_as_results(ds, revrange, since, branch, onto, message)
        if script:
            handler = _get_script_handler(script, since, revision)
        elif report:
            handler = _report
        else:
            handler = partial(_rerun, assume_ready=assume_ready,
                              explicit=explicit, jobs=jobs)

        for res in handler(ds, results):
            yield res


def _revrange_as_results(dset, revrange):
    ds_repo = dset.repo
    rev_lines = ds_repo.get_revisions(
        revrange, fmt="%H %P", options=["--reverse", "--topo-order"])
    if not rev_lines:
        return

    for rev_line in rev_lines:
        # The strip() below is necessary because, with the format above, a
        # commit without any parent has a trailing space. (We could also use a
        # custom `rev-list --parents ...` call to avoid this.)
        fields = rev_line.strip().split(" ")
        rev, parents = fields[0], fields[1:]
        res = get_status_dict("run", ds=dset, commit=rev, parents=parents)
        full_msg = ds_repo.format_commit("%B", rev)
        try:
            msg, info = get_run_info(dset, full_msg)
        except ValueError as exc:
            # Recast the error so the message includes the revision.
            raise ValueError(
                "Error on {}'s message".format(rev)) from exc

        if info is not None:
            if len(parents) != 1:
                lgr.warning(
                    "%s has run information but is a %s commit; "
                    "it will not be re-executed",
                    rev,
                    "merge" if len(parents) > 1 else "root")
                continue
            res["run_info"] = info
            res["run_message"] = msg
        yield dict(res, status="ok")


def _rerun_as_results(dset, revrange, since, branch, onto, message):
    """Represent the rerun as result records.

    In the standard case, the information in these results will be used to
    actually re-execute the commands.
    """

    try:
        results = _revrange_as_results(dset, revrange)
    except ValueError as exc:
        ce = CapturedException(exc)
        yield get_status_dict("run", status="error", message=str(ce),
                              exception=ce)
        return

    ds_repo = dset.repo
    # Drop any leading commits that don't have a run command. These would be
    # skipped anyways.
    results = list(dropwhile(lambda r: "run_info" not in r, results))
    if not results:
        yield get_status_dict(
            "run", status="impossible", ds=dset,
            message=("No run commits found in range %s", revrange))
        return

    if onto is not None and onto.strip() == "":
        onto = results[0]["commit"] + "^"

    if onto and not ds_repo.commit_exists(onto):
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
            # Resolve this to the full hexsha so downstream code gets a
            # predictable form.
            commit=ds_repo.get_hexsha(start_point),
            branch=branch,
            rerun_action="checkout",
            status="ok")

    def skip_or_pick(hexsha, result, msg):
        result["rerun_action"] = "skip-or-pick"
        shortrev = ds_repo.get_hexsha(hexsha, short=True)
        result["message"] = (
            "%s %s; %s",
            shortrev, msg, "skipping or cherry picking")

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
            if len(res["parents"]) > 1:
                res["rerun_action"] = "merge"
            else:
                skip_or_pick(hexsha, res, "does not have a command")
        yield res


def _mark_nonrun_result(result, which):
    msg = dict(skip="skipping", pick="cherry picking")[which]
    result["rerun_action"] = which
    result["message"] = result["message"][:-1] + (msg,)
    return result


def _rerun(dset, results, assume_ready=None, explicit=False, jobs=None):
    ds_repo = dset.repo
    # Keep a map from an original hexsha to a new hexsha created by the rerun
    # (i.e. a reran, cherry-picked, or merged commit).
    new_bases = {}  # original hexsha => reran hexsha
    branch_to_restore = ds_repo.get_active_branch()
    head = onto = ds_repo.get_hexsha()
    for res in results:
        lgr.info(_get_rerun_log_msg(res))
        rerun_action = res.get("rerun_action")
        if not rerun_action:
            yield res
            continue

        res_hexsha = res["commit"]
        if rerun_action == "checkout":
            if res.get("branch"):
                branch = res["branch"]
                checkout_options = ["-b", branch]
                branch_to_restore = branch
            else:
                checkout_options = ["--detach"]
                branch_to_restore = None
            ds_repo.checkout(res_hexsha,
                             options=checkout_options)
            head = onto = res_hexsha
            continue

        # First handle the two cases that don't require additional steps to
        # identify the base, a root commit or a merge commit.

        if not res["parents"]:
            _mark_nonrun_result(res, "skip")
            yield res
            continue

        if rerun_action == "merge":
            old_parents = res["parents"]
            new_parents = [new_bases.get(p, p) for p in old_parents]
            if old_parents == new_parents:
                if not ds_repo.is_ancestor(res_hexsha, head):
                    ds_repo.checkout(res_hexsha)
            elif res_hexsha != head:
                if ds_repo.is_ancestor(res_hexsha, onto):
                    new_parents = [p for p in new_parents
                                   if not ds_repo.is_ancestor(p, onto)]
                if new_parents:
                    if new_parents[0] != head:
                        # Keep the direction of the original merge.
                        ds_repo.checkout(new_parents[0])
                    if len(new_parents) > 1:
                        msg = ds_repo.format_commit("%B", res_hexsha)
                        ds_repo.call_git(
                            ["merge", "-m", msg,
                             "--no-ff", "--allow-unrelated-histories"] +
                            new_parents[1:])
                    head = ds_repo.get_hexsha()
                    new_bases[res_hexsha] = head
            yield res
            continue

        # For all the remaining actions, first make sure we're on the
        # appropriate base.

        parent = res["parents"][0]
        new_base = new_bases.get(parent)
        head_to_restore = None  # ... to find our way back if we skip.

        if new_base:
            if new_base != head:
                ds_repo.checkout(new_base)
                head_to_restore, head = head, new_base
        elif parent != head and ds_repo.is_ancestor(onto, parent):
            if rerun_action == "run":
                ds_repo.checkout(parent)
                head = parent
            else:
                _mark_nonrun_result(res, "skip")
                yield res
                continue
        else:
            if parent != head:
                new_bases[parent] = head

        # We've adjusted base. Now skip, pick, or run the commit.

        if rerun_action == "skip-or-pick":
            if ds_repo.is_ancestor(res_hexsha, head):
                _mark_nonrun_result(res, "skip")
                if head_to_restore:
                    ds_repo.checkout(head_to_restore)
                    head, head_to_restore = head_to_restore, None
                yield res
                continue
            else:
                ds_repo.cherry_pick(res_hexsha)
                _mark_nonrun_result(res, "pick")
                yield res
        elif rerun_action == "run":
            run_info = res["run_info"]
            # Keep a "rerun" trail.
            if "chain" in run_info:
                run_info["chain"].append(res_hexsha)
            else:
                run_info["chain"] = [res_hexsha]

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
                                 assume_ready=assume_ready,
                                 explicit=explicit,
                                 rerun_outputs=auto_outputs,
                                 message=message,
                                 jobs=jobs,
                                 rerun_info=run_info):
                yield r
        new_head = ds_repo.get_hexsha()
        if new_head not in [head, res_hexsha]:
            new_bases[res_hexsha] = new_head
        head = new_head

    if branch_to_restore:
        # The user asked us to replay the sequence onto a branch, but the
        # history had merges, so we're in a detached state.
        ds_repo.update_ref("refs/heads/" + branch_to_restore,
                           "HEAD")
        ds_repo.checkout(branch_to_restore)


def _get_rerun_log_msg(res):
    "Prepare log message for a rerun to summarize an action about to happen"
    msg = ''
    rerun_action = res.get("rerun_action")
    if rerun_action:
        msg += rerun_action
    if res.get('commit'):
        msg += " commit %s;" % res.get('commit')[:7]
    rerun_run_message = res.get("run_message")
    if rerun_run_message:
        if len(rerun_run_message) > 20:
            rerun_run_message = rerun_run_message[:17] + '...'
        msg += " (%s)" % rerun_run_message
    rerun_message = res.get("message")
    if rerun_message:
        msg += " " + rerun_message[0] % rerun_message[1:]
    msg = msg.lstrip()
    return msg


def _report(dset, results):
    ds_repo = dset.repo
    for res in results:
        if "run_info" in res:
            if res["status"] != "impossible":
                res["diff"] = list(res["diff"])
                # Add extra information that is useful in the report but not
                # needed for the rerun.
                out = ds_repo.format_commit("%an%x00%aI", res["commit"])
                res["author"], res["date"] = out.split("\0")
        yield res


def _get_script_handler(script, since, revision):
    ofh = sys.stdout if script.strip() == "-" else open(script, "w")

    def fn(dset, results):
        ds_repo = dset.repo
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
            revision=ds_repo.get_hexsha(revision),
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
            commit_descr = ds_repo.describe(res["commit"])
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
            'cannot rerun command, command specification is not valid JSON'
        ) from e
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

    def changed(res):
        return res.get("action") == "diff" and res.get("state") != "clean"

    diff = dataset.diff(recursive=True,
                        fr=fr, to=revision,
                        result_filter=changed,
                        return_type='generator', result_renderer='disabled')
    for r in diff:
        yield r


def new_or_modified(diff_results):
    """Filter diff result records to those for new or modified files.
    """
    for r in diff_results:
        if r.get('type') in ('file', 'symlink') \
                and r.get('state') in ['added', 'modified']:
            r.pop('status', None)
            yield r
