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

from os import linesep
from ...support.exceptions import CommandError
from ...dochelpers import exc_str


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
                      "--pretty=format:\"%H%n%B\""]
    out, err = _excute_by_item(cmd=lookup_sha_cmd, item=item, exc=exc,
                               runner=runner, cwd=cwd)
    lines = out.strip('\"').splitlines()
    commit_sha = lines[0]
    commit_msg = linesep.join(lines[1:]).strip().strip('\"')

    return commit_sha, commit_msg

