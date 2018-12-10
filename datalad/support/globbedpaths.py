# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Wrapper for globbing paths.
"""

import glob
import logging
import os.path as op

from datalad.utils import assure_unicode
from datalad.utils import chpwd
from datalad.utils import getpwd
from datalad.utils import partition

lgr = logging.getLogger('datalad.support.globbedpaths')


class GlobbedPaths(object):
    """Helper for globbing paths.

    Parameters
    ----------
    patterns : list of str
        Call `glob.glob` with each of these patterns. "." is considered as
        datalad's special "." path argument; it is not passed to glob and is
        always left unexpanded. Each set of glob results is sorted
        alphabetically.
    pwd : str, optional
        Glob in this directory.
    expand : bool, optional
       Whether the `paths` property returns unexpanded or expanded paths.
    """

    def __init__(self, patterns, pwd=None, expand=False):
        self.pwd = pwd or getpwd()
        self._expand = expand

        if patterns is None:
            self._maybe_dot = []
            self._paths = {"patterns": [], "sub_patterns": {}}
        else:
            patterns = list(map(assure_unicode, patterns))
            patterns, dots = partition(patterns, lambda i: i.strip() == ".")
            self._maybe_dot = ["."] if list(dots) else []
            self._paths = {
                "patterns": [op.relpath(p, start=pwd) if op.isabs(p) else p
                             for p in patterns],
                "sub_patterns": {}}

    def __bool__(self):
        return bool(self._maybe_dot or self.expand())

    __nonzero__ = __bool__  # py2

    def _get_sub_patterns(self, pattern):
        """Extract sub-patterns from the leading path of `pattern`.

        The right-most path component is successively peeled off until there
        are no patterns left.
        """
        if pattern in self._paths["sub_patterns"]:
            return self._paths["sub_patterns"][pattern]

        head, tail = op.split(pattern)
        if not tail:
            # Pattern ended with a separator. Take the first directory as the
            # base.
            head, tail = op.split(head)

        sub_patterns = []
        seen_magic = glob.has_magic(tail)
        while head:
            new_head, tail = op.split(head)
            if seen_magic and not glob.has_magic(head):
                break
            elif not seen_magic and glob.has_magic(tail):
                seen_magic = True

            if seen_magic:
                sub_patterns.append(head + op.sep)
            head = new_head
        self._paths["sub_patterns"][pattern] = sub_patterns
        return sub_patterns

    def _expand_globs(self):
        def normalize_hit(h):
            normalized = op.relpath(h) + ("" if op.basename(h) else op.sep)
            if h == op.curdir + op.sep + normalized:
                # Don't let relpath prune "./fname" (gh-3034).
                return h
            return normalized

        expanded = []
        with chpwd(self.pwd):
            for pattern in self._paths["patterns"]:
                hits = glob.glob(pattern)
                if hits:
                    expanded.extend(sorted(map(normalize_hit, hits)))
                else:
                    lgr.debug("No matching files found for '%s'", pattern)
                    # We didn't find a hit for the complete pattern. If we find
                    # a sub-pattern hit, that may mean we have an uninstalled
                    # subdataset.
                    for sub_pattern in self._get_sub_patterns(pattern):
                        sub_hits = glob.glob(sub_pattern)
                        if sub_hits:
                            expanded.extend(
                                sorted(map(normalize_hit, sub_hits)))
                            break
                    # ... but we still want to retain the original pattern
                    # because we don't know for sure at this point, and it
                    # won't bother the "install, reglob" routine.
                    expanded.extend([pattern])
        return expanded

    def expand(self, full=False, dot=True, refresh=False):
        """Return paths with the globs expanded.

        Parameters
        ----------
        full : bool, optional
            Return full paths rather than paths relative to `pwd`.
        dot : bool, optional
            Include the "." pattern if it was specified.
        refresh : bool, optional
            Run glob regardless of whether there are cached values. This is
            useful if there may have been changes on the file system.
        """
        maybe_dot = self._maybe_dot if dot else []
        if not self._paths["patterns"]:
            return maybe_dot + []

        if refresh or "expanded" not in self._paths:
            paths = self._expand_globs()
            self._paths["expanded"] = paths
        else:
            paths = self._paths["expanded"]

        if full:
            if refresh or "expanded_full" not in self._paths:
                paths = [op.join(self.pwd, p) for p in paths]
                self._paths["expanded_full"] = paths
            else:
                paths = self._paths["expanded_full"]

        return maybe_dot + paths

    @property
    def paths(self):
        """Return paths relative to `pwd`.

        Globs are expanded if `expand` was set to true during instantiation.
        """
        if self._expand:
            return self.expand()
        return self._maybe_dot + self._paths["patterns"]
