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
import json
import re

from datalad.interface.base import Interface
from datalad.interface.utils import eval_results
from datalad.interface.base import build_doc
from datalad.interface.results import get_status_dict
from datalad.interface.run import run_command
from datalad.interface.common_opts import save_message_opt

from datalad.support.constraints import EnsureNone
from datalad.support.param import Parameter

from datalad.distribution.dataset import require_dataset
from datalad.distribution.dataset import EnsureDataset
from datalad.distribution.dataset import datasetmethod

lgr = logging.getLogger('datalad.interface.run')


@build_doc
class Rerun(Interface):
    """Re-execute the previous `datalad run` command.

    This will unlock any dataset content that is on record to have
    been modified by the previous command run. It will then re-execute
    the command in the recorded path (if it was inside the
    dataset). Afterwards, all modifications will be saved.
    """
    _params_ = dict(
        dataset=Parameter(
            args=("-d", "--dataset"),
            doc="""specify the dataset from which to rerun a recorded command.
            If no dataset is given, an attempt is made to identify the dataset
            based on the current working directory. If a dataset is given,
            the command will be executed in the root directory of this
            dataset.""",
            constraints=EnsureDataset() | EnsureNone()),
        message=save_message_opt,
        # TODO
        # --list-commands
        #   go through the history and report any recorded command. this info
        #   could be used to unlock the associated output files for a rerun
    )

    @staticmethod
    @datasetmethod(name='rerun')
    @eval_results
    def __call__(
            dataset=None,
            message=None):

        ds = require_dataset(
            dataset, check_installed=True,
            purpose='rerunning a command')

        lgr.debug('rerunning command output underneath %s', ds)

        from datalad.tests.utils import ok_clean_git
        try:
            ok_clean_git(ds.path)
        except AssertionError:
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
                message='cannot re-run command, nothing recorded')
            return

        # pull run info out of the last commit message
        try:
            rec_msg, runinfo = get_commit_runinfo(ds.repo)
        except ValueError as exc:
            yield dict(
                err_info, status='error',
                message=str(exc)
            )
            return
        if not runinfo:
            yield dict(
                err_info, status='impossible',
                message=('cannot re-run command, last saved state does not '
                         'look like a recorded command run'))
            return

        # now we have to find out what was modified during the last run, and enable re-modification
        # ideally, we would bring back the entire state of the tree with #1424, but we limit ourself
        # to file addition/not-in-place-modification for now
        for r in ds.unlock(new_or_modified(ds),
                           return_type='generator', result_xfm=None):
            yield r

        for r in run_command(runinfo['cmd'], ds, rec_msg or message,
                             rerun_info=runinfo):
            yield r


def get_commit_runinfo(repo, commit=None):
    """Return message and run record from a commit message

    If none found - returns None, None; if anything goes wrong - throws
    ValueError with the message describing the issue
    """
    assert commit is None, "TODO: implement for anything but the last commit"
    last_commit_msg = repo.repo.head.commit.message
    cmdrun_regex = r'\[DATALAD RUNCMD\] (.*)=== Do not change lines below ' \
                   r'===\n(.*)\n\^\^\^ Do not change lines above \^\^\^'
    runinfo = re.match(cmdrun_regex, last_commit_msg,
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
    diff = dataset.diff(recursive=True,
                        revision="{rev}^..{rev}".format(rev=revision),
                        return_type='generator', result_renderer=None)
    for r in diff:
        if r.get('type') == 'file' and r.get('state') in ['added', 'modified']:
            r.pop('status', None)
            yield r
