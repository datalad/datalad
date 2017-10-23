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
from .exc import TestRepoError

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


def _get_commits_from_disc(item, exc=None, runner=None, cwd=None, options=None):

    lookup_commits_cmd = ['git', 'log', '--name-only']
    if options:
        lookup_commits_cmd.extend(options)
    lookup_commits_cmd.append('--pretty=format:start commit: %H %h%nparents: %P'
                              '%nmessage: %B%nend commit')

    #   --name-only
    #       Show only names of changed files.
    # TODO: At some point we might want to switch to even record the status
    # files were committed with:
    #   --name-status
    #       Show only names and status of changed files.

    # placeholders to use in format string:

    # %n: newline (=> works for others as well)

    # %H: commit hash
    # %h: abbreviated commit hash
    # %P: parent hashes (=>  space separated)
    # %p: abbreviated parent hashes
    # %d: ref names, like the --decorate option of git-log(1)
    # %D: ref names without the " (", ")" wrapping.
    # %s: subject
    # %f: sanitized subject line, suitable for a filename
    # %b: body
    # %B: raw body (unwrapped subject and body)

    out, err = _excute_by_item(cmd=lookup_commits_cmd, item=item, exc=exc,
                               runner=runner, cwd=cwd)

    from .items import Commit

    # ... circular import?
    from .items import ItemRepo
    if isinstance(item, ItemRepo):
        repo = item
    elif hasattr(item, 'repo'):
        repo = item.repo
    elif hasattr(item, '_repo'):
        repo = item._repo
    else:
        # WTF
        raise TestRepoError("MEEEEH")

    lines = out.splitlines()
    commits = []
    paths = []
    full_sha = None
    short_sha = None
    parent_shas = None
    lineidx = 0
    while lineidx < len(lines):
        if lines[lineidx].startswith('start commit: '):
            full_sha, short_sha = lines[lineidx][14:].split()
            lineidx += 1
            continue
        if lines[lineidx].startswith('parents: '):
            parent_shas = lines[lineidx][9:].split()
            lineidx += 1
            continue
        if lines[lineidx].startswith('message: '):
            message = lines[lineidx][9:]
            lineidx += 1
            while not lines[lineidx].startswith('end commit'):
                message += lines[lineidx]
                lineidx += 1
            while lineidx < len(lines) and \
                    not lines[lineidx].startswith('start commit: '):
                # we have a path to register with this commit
                if lines[lineidx]:
                    paths.append(lines[lineidx].strip())
                lineidx += 1

            # we retrieved everything. build the commit:
            commits.append(Commit(repo=repo, sha=full_sha, short=short_sha,
                                  parents=parent_shas, message=message,
                                  paths=paths))
            # reset everything and proceed
            paths = []
            full_sha = None
            short_sha = None
            parent_shas = None
            continue
        # we should never get here
        # either format was changed, without adjusting parsing accordingly or
        # something unexpected happened.

        msg = "Output parsing for git-log failed at line {idx}:{ls}{line}" \
              "".format(idx=lineidx,
                        ls=linesep,
                        line=lines[lineidx])
        if exc:
            exc.message += msg
        else:
            exc = RuntimeError(msg)
        raise exc

    return commits


def _get_last_commit_from_disc(item, exc=None, runner=None, cwd=None):
    """convenience helper

    Returns
    -------
    Commit
    """

    commit = _get_commits_from_disc(item=item, exc=exc, runner=runner, cwd=cwd,
                                    options=['-n', '1'])
    assert(len(commit) == 1)
    return commit[0]


def _get_branches_from_disc(item, exc=None, runner=None, cwd=None,
                            options=None):

    from .items import Branch

    branch_cmd = ['git', 'branch']
    if options:
        branch_cmd.extend(options)
    branch_cmd.extend(['-a', '-v', '-v'])

    out, err = _excute_by_item(branch_cmd, item=item, exc=exc,
                               runner=runner, cwd=cwd)

    # Example outputs including remote branches, possible tracking branches, commits, ...
    # % git branch -a -v -v
    #  0.5.x                                                    28beca1a [origin/0.5.x: behind 4] Merge pull request #1534 from yarikoptic/bf-sphinx
    #  bf-1275                                                  0d5d41c5 [gh-mih/bf-1275] RF: Do not place default push config on publish anymore
    #  bf-1319                                                  af3be13d BF: Correct assertion to check what we are actually interested in. (Closes #1319)
    #* rf-testrepos                                             6d0f4caa ENH: Make TestRepos actually lazy. We need to reference persistent ones in other TestRepos using them. Therefore the laziness wasn't real, since the simple import of repos.py instantiated all of them, that were referenced this way. Now, the 'src' parameter of an ItemRepo isn't required to be an ItemRepo anymore, but is allowed to be a callable.
    #  remotes/origin/HEAD                                      -> origin/master
    #* (HEAD detached at 94ac5bf)                               94ac5bf Adding a rudimentary git-annex load file

    branches = []
    lines = out.splitlines()

    # ... circular import?
    from .items import ItemRepo
    if isinstance(item, ItemRepo):
        repo = item
    elif hasattr(item, 'repo'):
        repo = item.repo
    elif hasattr(item, '_repo'):
        repo = item._repo
    else:
        # WTF
        raise TestRepoError("MEEEEH")

    for line in lines:

        is_head = False
        if line[0] == '*':
            is_head = True
        if "HEAD detached" in line:
            if not is_head:
                # WTF?
                raise
            name = 'HEAD'
            (head, sep, tail) = line.partition(')')
            remainder = tail.lstrip()
        else:
            name = line[2:].split()[0]
            remainder = line[3+len(name):].lstrip()
        if remainder.startswith('->'):
            points_to = remainder[2:].strip()
            points_to = "remotes/" + points_to
            short_sha = None
            upstream = None
        else:
            points_to = None
            short_sha = remainder.split()[0]
            remainder = remainder[len(short_sha)+1:]
            if remainder.startswith('['):
                idx = remainder.find(']')
                upstream = remainder[1:idx].split()[0].rstrip(':')
                upstream = "remotes/" + upstream
                # remainder = remainder[idx+1:] # Not used currently
            else:
                upstream = None
            # message = remainder.strip() # Not used currently

        branches.append(Branch(name=name, repo=repo,
                               commit=short_sha,
                               upstream=upstream,
                               points_to=points_to,
                               is_active=is_head))
        if is_head and name != 'HEAD':
            # derive special branch 'HEAD' in addition:
            branches.append(Branch(name='HEAD', repo=repo, commit=None,
                                   upstream=None, points_to=name,
                                   is_active=False)
                            )

    return branches


def _get_branch_from_commit(item, commit, exc=None, runner=None, cwd=None):
    """convenience helper

    look up the branches containing a given commit
    Intended to be used when committing to determine what branch we are at.
    Note, that git-status is to be avoided as far as possible, due to issues in
    direct mode submodules and performance.

    Returns
    -------
    list of Branch
    """

    return _get_branches_from_disc(item=item, exc=exc, runner=runner, cwd=cwd,
                                   options=['--contains', commit.sha])


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

    from git import GitConfigParser, Repo
    from .items import Remote

    # Note: This would fail with a .git file
    # We might need to have a git.Repo to access it's config_reader.
    # Also note, that to make instantiation of git.Repo cheaper, we could
    # fake an ObjectDB class with an empty constructor, since we actually need
    # the discovery of correct git config only.
    class FakeDB(object):
        def __init__(self, *args):
            pass

    with Repo(repo.path, odbt=FakeDB) as r:
        cp = r.config_reader(config_level='repository')
        remotes = []
        for r_sec in [sec for sec in cp.sections() if sec.startswith("remote")]:
            name = r_sec[8:-1]
            settings = dict()
            for r_opt in cp.options(section=r_sec):
                settings[r_opt] = cp.get_value(r_sec, r_opt)
            remotes.append(Remote(name, settings))

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


def get_ancestry(commit, include=True):

    if not commit.parents:
        return [commit] if include else []

    parents = [commit] if include else []
    for c in commit.parents:
        parents.extend(get_ancestry(c, include=True))

    return parents


# TODO: melt in with datalad.utils.unique
def unique_via_equals(seq):

    seen = set()
    seen_add = seen.add

    def in_seen(x):
        return any(x == i for i in seen)

    return [x for x in seq if not (in_seen(x) or seen_add(x))]
