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

# TODO: RF and move all paths related functions from datalad.utils in here
import os
import os.path as op

# to not pollute API importing as _
from collections import defaultdict as _defaultdict

from functools import wraps
from itertools import dropwhile

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


def robust_abspath(p):
    """A helper which would not fail if p is relative and we are in non-existing directory

    It will rely on getpwd, which would rely on $PWD env variable to report
    the path.  Desired for improved resilience during e.g. reporting as in
    https://github.com/datalad/datalad/issues/2787
    """
    try:
        return abspath(p)
    except OSError as exc:
        if not isabs(p):
            try:
                os.getcwd()
                # if no exception raised it was not the reason, raise original
                raise
            except:
                return normpath(join(getpwd(), p))
        raise


def split_ext(filename):
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


def get_parent_paths(paths, parents, only_with_parents=False, *, sep='/'):
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
    parents = set(parents)  # O(log(len(parents))) lookup

    # Will be used in sanity checking that we got consistently used separators, i.e.
    # not mixing non-POSIX paths and POSIX parents
    asep = {'/': '\\', '\\': '/'}[sep]

    # rely on path[:n] be quick, and len(parent_lengths) << len(parents)
    # when len(parents) is large.  We will also bail checking any parent of
    # the length if at that length path has no directory boundary ('/').
    #
    # Create mapping for each length of
    # parent path to list of parents with that length
    parent_lengths = _defaultdict(set)
    for parent in parents:
        _get_parent_paths_check(parent, sep, asep)
        parent_lengths[len(parent)].add(parent)

    # Make it ordered in the descending order so we select the deepest/longest parent
    # and store them as sets for faster lookup.
    # Could be an ordered dict but no need
    parent_lengths = [(l, parent_lengths[l]) for l in sorted(parent_lengths, reverse=True)]

    res = []
    seen = set()

    for path in paths:  # O(len(paths)) - unavoidable but could be parallelized!
        # Sanity check -- should not be too expensive
        _get_parent_paths_check(path, sep, asep)
        for parent_length, parents_ in parent_lengths:  # O(len(parent_lengths))
            if (len(path) < parent_length) or (len(path) > parent_length and path[parent_length] != sep):
                continue  # no directory deep enough
            candidate_parent = path[:parent_length]
            if candidate_parent in parents_:  # O(log(len(parents))) but expected one less due to per length handling
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


def _get_parent_paths_check(path, sep, asep):
    """A little helper for get_parent_paths"""
    if isabs(path) or path.startswith(pardir + sep) or path.startswith(curdir + sep):
        raise ValueError("Expected relative within directory paths, got %r" % path)
    if sep+sep in path:
        raise ValueError(f"Expected normalized paths, got {path} containing '{sep+sep}'")
    if asep in path:
        raise ValueError(f"Expected paths with {sep} as separator, got {path} containing '{asep}'")
