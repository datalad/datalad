# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
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

from functools import wraps
from itertools import dropwhile

from ..utils import (
    assure_bytes,
    getpwd,
)


def _get_unicode_robust_version(f):

    @wraps(f)
    def wrapped(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except UnicodeEncodeError:
            return f(assure_bytes(*args, **kwargs))
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
    >>> from datalad.plugin.addurls import split_ext
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