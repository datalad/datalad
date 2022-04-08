# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Wrapper for globbing paths.
"""

import glob
from functools import lru_cache
from itertools import chain
import logging
import os.path as op

from datalad.utils import chpwd
from datalad.utils import ensure_unicode
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
            self._patterns = []
        else:
            patterns = list(map(ensure_unicode, patterns))
            patterns, dots = partition(patterns, lambda i: i.strip() == ".")
            self._maybe_dot = ["."] if list(dots) else []
            self._patterns = [op.relpath(p, start=pwd) if op.isabs(p) else p
                              for p in patterns]
        self._cache = {}

    def __bool__(self):
        return bool(self._maybe_dot or self._patterns)

    @staticmethod
    @lru_cache()
    def _get_sub_patterns(pattern):
        """Extract sub-patterns from the leading path of `pattern`.

        The right-most path component is successively peeled off until there
        are no patterns left.
        """
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
        return sub_patterns

    def _expand_globs(self):
        def normalize_hit(h):
            normalized = op.relpath(h) + ("" if op.basename(h) else op.sep)
            if h == op.curdir + op.sep + normalized:
                # Don't let relpath prune "./fname" (gh-3034).
                return h
            return normalized

        hits = {}
        partial_hits = {}
        misses = {}
        with chpwd(self.pwd):
            for pattern in self._patterns:
                full_hits = glob.glob(pattern, recursive=True)
                if full_hits:
                    hits[pattern] = sorted(map(normalize_hit, full_hits))
                else:
                    lgr.debug("No matching files found for '%s'", pattern)
                    # We didn't find a hit for the complete pattern. If we find
                    # a sub-pattern hit, that may mean we have an uninstalled
                    # subdataset.
                    for sub_pattern in self._get_sub_patterns(pattern):
                        sub_hits = glob.glob(sub_pattern, recursive=True)
                        if sub_hits:
                            partial_hits[pattern] = sorted(
                                map(normalize_hit, sub_hits))
                            break
                    else:
                        misses[pattern] = [pattern]
        return hits, partial_hits, misses

    def expand(self, full=False, dot=True, refresh=False,
               include_partial=True, include_misses=True):
        """Return paths with the globs expanded.

        Globbing is done with `glob.glob`. If a pattern doesn't have a match,
        the trailing path component of the pattern is removed and, if any globs
        remain, `glob.glob` is called again with the new pattern. This
        procedure is repeated until a pattern matches or there are no more
        patterns.

        Parameters
        ----------
        full : bool, optional
            Return full paths rather than paths relative to `pwd`.
        dot : bool, optional
            Include the "." pattern if it was specified.
        refresh : bool, optional
            Run glob regardless of whether there are cached values. This is
            useful if there may have been changes on the file system.
        include_partial : bool, optional
            Whether the results include sub-pattern hits (see description
            above) when the full pattern doesn't match.
        include_misses : : bool, optional
            Whether the results include the original pattern when there are no
            matches for a pattern or its sub-patterns (see description above).
        """
        if refresh:
            self._cache = {}

        maybe_dot = self._maybe_dot if dot else []
        if not self._patterns:
            return maybe_dot + []

        if "hits" not in self._cache:
            hits, partial_hits, misses = self._expand_globs()
            self._cache["hits"] = hits
            self._cache["partial_hits"] = partial_hits
            self._cache["misses"] = misses
        else:
            hits = self._cache["hits"]
            partial_hits = self._cache["partial_hits"]
            misses = self._cache["misses"]

        key_suffix = (include_partial, include_misses)
        key_expanded = ("expanded",) + key_suffix
        if key_expanded not in self._cache:
            sources = [hits]
            if include_partial:
                sources.append(partial_hits)
            if include_misses:
                sources.append(misses)

            paths = []
            for pattern in self._patterns:
                for source in sources:
                    if pattern in source:
                        paths.extend(source[pattern])
                        break
            self._cache[key_expanded] = paths
        else:
            paths = self._cache[key_expanded]

        if full:
            key_full = ("expanded_full",) + key_suffix
            if key_full not in self._cache:
                paths = [op.join(self.pwd, p) for p in paths]
                self._cache[key_full] = paths
            else:
                paths = self._cache[key_full]

        return maybe_dot + paths

    def expand_strict(self, full=False, dot=True, refresh=False):
        return self.expand(full=full, dot=dot, refresh=refresh,
                           include_partial=False, include_misses=False)

    def _chain(self, what):
        if self._patterns:
            if "hits" not in self._cache:
                self.expand()
            # Note: This assumes a preserved insertion order for dicts, which
            # is true with our current minimum python version (3.6) and part of
            # the language spec as of 3.7.
            return list(chain(*self._cache[what].values()))
        return []

    @property
    def partial_hits(self):
        """Return patterns that had a partial but not complete match.
        """
        return self._chain("partial_hits")

    @property
    def misses(self):
        """Return patterns that didn't have any complete or partial matches.

        This doesn't include patterns where a sub-pattern matched. Those are
        available via `partial_hits`.
        """
        return self._chain("misses")

    @property
    def paths(self):
        """Return paths relative to `pwd`.

        Globs are expanded if `expand` was set to true during instantiation.
        """
        if self._expand:
            return self.expand()
        return self._maybe_dot + self._patterns
