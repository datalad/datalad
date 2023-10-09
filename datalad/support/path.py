# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Helper functionality and overloads for paths treatment

One of the reasons is also to robustify operation with unicode filenames
"""
from __future__ import annotations

# TODO: RF and move all paths related functions from datalad.utils in here
import os
import os.path as op
# to not pollute API importing as _
from collections import defaultdict as _defaultdict
from collections.abc import (
    Iterable,
    Iterator,
)
from functools import wraps
from itertools import dropwhile
from pathlib import (
    Path,
    PurePosixPath,
)

from ..utils import (
    ensure_bytes,
    getpwd,
)


def _get_unicode_robust_version(f):

    @wraps(f)
    def wrapped(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except UnicodeEncodeError:
            return f(ensure_bytes(*args, **kwargs))
    doc = getattr(f, '__doc__', None)
    # adjust only if __doc__ is not completely absent (None)
    if doc is not None:
        wrapped.__doc__ = doc + \
            "\n\nThis wrapper around original function would encode forcefully " \
            "to utf-8 if initial invocation fails"
    return wrapped


abspath = op.abspath
basename = op.basename
curdir = op.curdir
dirname = op.dirname
exists = _get_unicode_robust_version(op.exists)
isdir = _get_unicode_robust_version(op.isdir)
isabs = _get_unicode_robust_version(op.isabs)
join = op.join
lexists = _get_unicode_robust_version(op.lexists)
normpath = op.normpath
pardir = op.pardir
pathsep = op.pathsep
relpath = op.relpath
realpath = _get_unicode_robust_version(op.realpath)
sep = op.sep


def robust_abspath(p: str | Path) -> str:
    """A helper which would not fail if p is relative and we are in non-existing directory

    It will rely on getpwd, which would rely on $PWD env variable to report
    the path.  Desired for improved resilience during e.g. reporting as in
    https://github.com/datalad/datalad/issues/2787
    """
    try:
        return abspath(p)
    except OSError:
        if not isabs(p):
            try:
                os.getcwd()
            except Exception:
                return normpath(join(getpwd(), p))
        # if no exception raised it was not the reason, raise original
        raise


def split_ext(filename: str) -> tuple[str, str]:
    """Use git-annex's splitShortExtensions rule for splitting extensions.

    Parameters
    ----------
    filename : str

    Returns
    -------
    A tuple with (root, extension)

    Examples
    --------
    >>> from datalad.local.addurls import split_ext
    >>> split_ext("filename.py")
    ('filename', '.py')

    >>> split_ext("filename.tar.gz")
    ('filename', '.tar.gz')

    >>> split_ext("filename.above4chars.ext")
    ('filename.above4chars', '.ext')
    """
    parts = filename.split(".")
    if len(parts) == 1:
        return filename, ""

    tail = list(dropwhile(lambda x: len(x) < 5,
                          reversed(parts[1:])))

    file_parts = parts[:1] + tail[::-1]
    ext_parts = parts[1+len(tail):]
    return ".".join(file_parts), "." + ".".join(ext_parts)


def get_parent_paths(paths: list[str], parents: list[str], only_with_parents: bool = False, *, sep: str = '/') -> list[str]:
    """Given a list of children paths, return their parent paths among parents
    or their own path if there is no known parent. A path is also considered its
    own parent (haven't you watched Predestination?) ;)

    All paths should be relative, not pointing outside (not starting
    with ../), and normalized (no // or dir/../dir and alike). Only minimal
    sanity checking of values is done.  By default paths are considered to be
    POSIX. Use 'sep' kwarg to set to `os.sep` to provide OS specific handling.

    Accent is made on performance to avoid O(len(paths) * len(parents))
    runtime.  ATM should be typically less than O(len(paths) * len(log(parents)))

    Initial intended use - for a list of paths in the repository
    to provide their paths as files/submodules known to that repository, to
    overcome difference in ls-tree and ls-files, where ls-files outputs nothing
    for paths within submodules.
    It is coded, so it could later be applied even whenever there are nested
    parents, e.g. parents = ['sub', 'sub/sub'] and then the "deepest" parent
    is selected

    Parameters
    ----------
    parents: list of str
    paths: list of str
    only_with_parents: bool, optional
      If set to True, return a list of only parent paths where that path had
      a parent
    sep: str, optional
      Path separator.  By default - '/' and thus treating paths as POSIX.
      If you are processing OS-specific paths (for both `parents` and `paths`),
      specify `sep=os.sep`.

    Returns
    -------
    A list of paths (without duplicates), where some entries replaced with
    their "parents" without duplicates.  So for 'a/b' and 'a/c' with a being
    among parents, there will be a single 'a'
    """
    # Let's do an early check even though then we would skip the checks on paths
    # being relative etc
    if not parents:
        return [] if only_with_parents else paths

    # We will create a lookup for known parent lengths
    parent_set = set(parents)  # O(log(len(parents))) lookup

    # Will be used in sanity checking that we got consistently used separators, i.e.
    # not mixing non-POSIX paths and POSIX parents
    asep = {'/': '\\', '\\': '/'}[sep]

    # rely on path[:n] be quick, and len(parent_lengths) << len(parent_set)
    # when len(parent_set) is large.  We will also bail checking any parent of
    # the length if at that length path has no directory boundary ('/').
    #
    # Create mapping for each length of
    # parent path to list of parents with that length
    parent_lengths_map: dict[int, set[str]] = _defaultdict(set)
    for parent in parent_set:
        _get_parent_paths_check(parent, sep, asep)
        parent_lengths_map[len(parent)].add(parent)

    # Make it ordered in the descending order so we select the deepest/longest parent
    # and store them as sets for faster lookup.
    # Could be an ordered dict but no need
    parent_lengths = [(l, parent_lengths_map[l]) for l in sorted(parent_lengths_map, reverse=True)]

    res = []
    seen = set()

    for path in paths:  # O(len(paths)) - unavoidable but could be parallelized!
        # Sanity check -- should not be too expensive
        _get_parent_paths_check(path, sep, asep)
        for parent_length, parents_ in parent_lengths:  # O(len(parent_lengths))
            if (len(path) < parent_length) or (len(path) > parent_length and path[parent_length] != sep):
                continue  # no directory deep enough
            candidate_parent = path[:parent_length]
            if candidate_parent in parents_:  # O(log(len(parent_set))) but expected one less due to per length handling
                if candidate_parent not in seen:
                    res.append(candidate_parent)
                    seen.add(candidate_parent)
                break  # it is!
        else:  # no hits
            if not only_with_parents:
                if path not in seen:
                    res.append(path)
                    seen.add(path)

    return res


def get_filtered_paths_(paths: Iterable[str|Path], filter_paths: Iterable[str | Path],
                        *, include_within_path: bool = False) \
        -> Iterator[str]:
    """Among paths (or Path objects) select the ones within filter_paths.

    All `paths` and `filter_paths` must be relative and POSIX.

    In case of `include_with_path=True`, if a `filter_path` points to some path
    under a `path` within `paths`, that path would be returned as well, e.g.
    `path` 'submod' would be returned if there is a `filter_path` 'submod/subsub/file'.

    Complexity is O(N*log(N)), where N is the largest of the lengths of `paths`
    or `filter_paths`.

    Yields
    ------
    paths, sorted (so order is not preserved), which reside under 'filter_paths' or
    path within 'filter_paths' is under that path.
    """
    # do conversion and sanity checks, O(N)
    def _harmonize_paths(l: Iterable[str | Path]) -> list[tuple[str, ...]]:
        ps = []
        for p in l:
            pp = PurePosixPath(p)
            if pp.is_absolute():
                raise ValueError(f"Got absolute path {p}, expected relative")
            if pp.parts and pp.parts[0] == '..':
                raise ValueError(f"Path {p} leads outside")
            ps.append(pp.parts)  # store parts
        return sorted(ps)  # O(N * log(N))

    paths_parts = _harmonize_paths(paths)
    filter_paths_parts = _harmonize_paths(filter_paths)

    # we will pretty much "scroll" through sorted paths and filter_paths at the same time
    for path_parts in paths_parts:
        while filter_paths_parts:
            filter_path_parts = filter_paths_parts[0]
            l = min(len(path_parts), len(filter_path_parts))
            # if common part is "greater" in the path -- we can go to the next "filter"
            if filter_path_parts[:l] < path_parts[:l]:
                # get to the next one
                filter_paths_parts = filter_paths_parts[1:]
            else:
                break  # otherwise -- consider this one!
        else:
            # no filter path left - the other paths cannot be the selected ones
            break
        if include_within_path:
            # if one identical or subpath of another one -- their parts match in the beginning
            # and we will just reuse that 'l'
            pass
        else:
            # if all components of the filter match, for that we also add len(path_parts) check below
            l = len(filter_path_parts)
        if len(path_parts) >= l and (path_parts[:l] == filter_path_parts[:l]):
            yield '/'.join(path_parts)


def _get_parent_paths_check(path: str, sep: str, asep: str) -> None:
    """A little helper for get_parent_paths"""
    if isabs(path) or path.startswith(pardir + sep) or path.startswith(curdir + sep):
        raise ValueError("Expected relative within directory paths, got %r" % path)
    if sep+sep in path:
        raise ValueError(f"Expected normalized paths, got {path} containing '{sep+sep}'")
    if asep in path:
        raise ValueError(f"Expected paths with {sep} as separator, got {path} containing '{asep}'")
