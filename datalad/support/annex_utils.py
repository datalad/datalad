# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Internal helper functions for interfacing git-annex
"""

from __future__ import annotations

from datalad.utils import ensure_list


def _fake_json_for_non_existing(paths: str | list[str], cmd: str) -> list[dict]:
    """Create faked JSON records for nonexisting paths provided by `paths`
    after running `cmd`.

    Internal helper for `AnnexRepo._call_annex_records`.

    Parameters:
    -----------
    paths: str or list of str
        paths to create annex-like JSON records for, communicating that the
        path is unknown.
    cmd: str
        annex cmd for which to fake this result
    """

    return [{"command": cmd,
             "file": f,
             "note": "not found",
             "success": False,
             "error-messages": ["File unknown to git"]  # Note,
             # that git's and annex' reporting here differs by config and
             # command on whether they say "does not exist" or "did not match
             # any file known to git".
             } for f in ensure_list(paths)]


def _get_non_existing_from_annex_output(output: str) -> list[str]:
    """This parses annex' output for messages about non-existing paths
    and returns a list of such paths (as strings).

    Internal helper for `_call_annex_records`.
    """

    # This should cease to exist whenever annex provides an actual API
    # for retrieving such information;
    # see https://git-annex.brachable.com/todo/api_for_telling_when_nonexistant_or_non_git_files_passed/

    # Output largely depends on annex config annex.skipunknown
    # (see https://github.com/datalad/datalad/pull/6510#issuecomment-1054499339)
    # and git-annex' default of annex.skipunknown changed as of 10.20220222.
    # However, that appears to not be true for all commands. annex-add would
    # still report in the "git-annex: ... not found" fashion rather than
    # "error:  ... did not match any file(s) known to git". Depends on
    # what annex is calling internally *and* on that config. Apparently git
    # itself isn't consistent in that regard.
    # Therefore, account for both ways of reporting unknown paths.

    unknown_paths = []
    for line in output.splitlines():
        if 'did not match any file(s) known to git' in line:
            unknown_paths.append(line[17:-40])
        elif line.startswith('git-annex:') and line.endswith(' not found'):
            unknown_paths.append(line[11:-10])

    return unknown_paths


def _sanitize_key(key: str) -> str:
    """Returns a sanitized key that is a suitable directory/file name

    Documentation from the analog implementation in git-annex
    Annex/Locations.hs

    Converts a key into a filename fragment without any directory.

    Escape "/" in the key name, to keep a flat tree of files and avoid
    issues with keys containing "/../" or ending with "/" etc.

    "/" is escaped to "%" because it's short and rarely used, and resembles
        a slash
    "%" is escaped to "&s", and "&" to "&a"; this ensures that the mapping
        is one to one.
    ":" is escaped to "&c", because it seemed like a good idea at the time.

    Changing what this function escapes and how is not a good idea, as it
    can cause existing objects to get lost.
    """
    esc = {
        '/': '%',
        '%': '&s',
        '&': '&a',
        ':': '&c',
    }
    return ''.join(esc.get(c, c) for c in key)
