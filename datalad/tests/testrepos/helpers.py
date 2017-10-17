# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Helpers for internal use by test repositories
"""

import logging
from os import linesep
from os.path import join as opj
from ...support.exceptions import CommandError
from ...dochelpers import exc_str

lgr = logging.getLogger('datalad.tests.testrepos.helpers')


def log(*args, **kwargs):
    """helper to log at a default level

    since this is not even about actual datalad tests, not to speak of actual
    datalad code, log at pretty low level.
    """
    lgr.log(5, *args, **kwargs)


def _excute_by_item(cmd, item, exc=None, runner=None, cwd=None):
    """

    Parameters
    ----------
    exc: TestRepoError
        predefined exception to raise instead of CommandError to give more
        information about when what item ran into the error.
    """

    runner = runner or item._runner

    from os.path import dirname
    from .items import ItemFile
    # Note, that if item is a file, it doesn't know where it belongs to. So, let
    # the actual call figure it out by calling in the file's directory by
    # default:
    cwd = cwd or (dirname(item.path) if isinstance(item, ItemFile)
                  else item.path)

    log("run %s from within %s", cmd, cwd)
    try:
        out, err = runner.run(cmd, cwd=cwd)
    except CommandError as e:
        if exc:
            # we got a predefined one. Use it:
            exc.message += " {it}({p}) ({e})".format(
                it=item.__class__,
                p=item.path,
                e=exc_str(e))
            exc.item = item.__class__
            raise exc
        else:
            # raise original
            raise e
    return out, err


def _get_last_commit_from_disc(item, exc=None, runner=None, cwd=None):
    """convenience helper

    Probably to RF, since we'll need similar ones. Just have them in one place
    already, in particular to have output parsing at a glance

    Returns
    -------
    tuple of str
        (commit SHA, commit message)
    """

    # TODO: - We probably need the date, too, in order to sort
    #       - or the parents
    #       => depends on how we get to discover structure of history. Right
    #       now, not everything can be set during creation.
    #       - If we ever get to test it, we may also need author etc.
    lookup_sha_cmd = ['git', 'log', '-n', '1',
                      "--pretty=format:%H%n%B"]
    out, err = _excute_by_item(cmd=lookup_sha_cmd, item=item, exc=exc,
                               runner=runner, cwd=cwd)
    lines = out.splitlines()
    commit_sha = lines[0]
    commit_msg = linesep.join(lines[1:])

    return commit_sha, commit_msg


def _get_commits_from_disc(item, exc=None, runner=None, cwd=None):

    lookup_commits_cmd = ['git', 'log', "--pretty=format:%H%n%B"]
    out, err = _excute_by_item(cmd=lookup_commits_cmd, item=item, exc=exc,
                               runner=runner, cwd=cwd)

    lines = out.splitlines()
    commits = []
    line_idx = 0
    while line_idx < len(lines):
        commit_sha = lines[line_idx]
        try:
            next_empty = line_idx + lines[line_idx:].index('')
        except ValueError:
            next_empty = len(lines)
        commit_msg = linesep.join(lines[line_idx+1:next_empty])
        commits.append((commit_sha, commit_msg))
        line_idx = next_empty + 1
    return commits


def _get_branch_from_commit(item, commit, exc=None, runner=None, cwd=None):
    """convenience helper

    look up the branches containing a given commit
    Intended to be used when committing to determine what branch we are at.
    Note, that git-status is to be avoided as far as possible, due to issues in
    direct mode submodules and performance.

    Returns
    -------
    list of str
    """

    lookup_branch_cmd = ['git', 'branch', '--contains', commit]
    out, err = _excute_by_item(lookup_branch_cmd, item=item, exc=exc,
                               runner=runner, cwd=cwd)
    return [line[2:] for line in out.splitlines()]


def _get_branches_from_disc(item, exc=None, runner=None, cwd=None):

    branch_cmd = ['git', 'branch', '-a']
    out, err = _excute_by_item(branch_cmd, item=item, exc=exc,
                               runner=runner, cwd=cwd)
    return [line[2:].split()[0] for line in out.splitlines()]


def _get_remotes_from_config(repo):
    """

    Parameters
    ----------
    repo: ItemRepo

    Returns
    -------
    tuple
        (name, dict)
        name of the remote, key-value dict of all options in the remote's
        section in git config
    """

    from git import GitConfigParser

    # Note: This would fail with a .git file
    # We might need to have a git.Repo to access it's config_reader.
    # Also note, that to make instantiation of git.Repo cheaper, we could
    # fake an ObjectDB class with an empty constructor, since we actually need
    # the discovery of correct git config only.
    cp = GitConfigParser(opj(repo.path, '.git', 'config'), read_only=True)
    remotes = []
    for r_sec in [sec for sec in cp.sections() if sec.startswith("remote")]:
        remote = (r_sec[8:-1], dict())
        for r_opt in cp.options(section=r_sec):
            remote[1][r_opt] = cp.get_value(r_sec, r_opt)
        remotes.append(remote)

    return remotes


def _get_submodules_from_disc(item, exc=None, runner=None, cwd=None):

    lookup_submodules_cmd = ['git', '--work-tree=.', 'submodule']

    out, err = _excute_by_item(lookup_submodules_cmd, item=item, exc=exc,
                               runner=runner, cwd=cwd)

    submodules = []
    for line in out.splitlines():
        st = line[0]
        sha = line[1:41]
        start_ref = line[42:].find('(')
        if start_ref > -1:
            path = line[42:42+start_ref-1]
            ref = line[42+start_ref:].lstrip('(').rstrip(')')
        else:
            path = line[42:]
            ref = None
        submodules.append((st, sha, path, ref))
    return submodules
