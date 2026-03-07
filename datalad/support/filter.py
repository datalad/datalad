# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Filter expression parsing and matching for recursion filtering.

Filter expressions allow selecting subdatasets based on their properties
during recursive operations. See docs/designs/recursion-filter.md for the
full design.

Expression syntax::

    KEY=VALUE         exact string match
    KEY!=VALUE        exact string non-match
    KEY~=REGEX        Python regex search (re.search)
    KEY!~REGEX        Python regex non-search
    KEY?              property exists and is non-empty
    KEY!?             property is absent or empty

Namespace rules:

- Bare keywords (``url``, ``name``, ``datalad-id``) map to
  ``gitmodule_<keyword>`` in the subdataset record.
- Dot-prefixed keywords (``.state``, ``.path``) map to internal properties
  in the subdataset record (dot stripped).
"""

from __future__ import annotations

import re

# Ordered so longer operators are tried first to avoid prefix conflicts
_OPERATORS = ['!~', '~=', '!=', '!?', '=', '?']

# Valid key pattern: dot-prefixed or bare keyword with alphanumeric and hyphens
_KEY_RE = re.compile(r'^\.?[A-Za-z][-A-Za-z0-9]*$')


def parse_filter_spec(expr: str) -> tuple[str, str, str]:
    """Parse a filter expression into a (key, operator, value) tuple.

    Parameters
    ----------
    expr : str
        A filter expression string like ``'url~=^\\.\\.'`` or ``.state=present``.

    Returns
    -------
    tuple of (str, str, str)
        ``(key, operator, value)`` where value is ``''`` for unary operators
        (``?``, ``!?``).

    Raises
    ------
    ValueError
        If the expression cannot be parsed.
    """
    if not expr or not isinstance(expr, str):
        raise ValueError(f"Invalid filter expression: {expr!r}")

    for op in _OPERATORS:
        idx = expr.find(op)
        if idx > 0:  # key must be non-empty (idx > 0)
            key = expr[:idx]
            if op in ('?', '!?'):
                # Unary operators: everything after key+op is ignored
                # but key+op must be the whole expression
                if idx + len(op) != len(expr):
                    continue
                value = ''
            else:
                value = expr[idx + len(op):]
            if not _KEY_RE.match(key):
                raise ValueError(
                    f"Invalid filter key {key!r} in expression {expr!r}: "
                    f"must start with a letter and contain only "
                    f"alphanumeric characters and hyphens")
            return (key, op, value)

    # Check for trailing ? or !? with valid key
    if expr.endswith('!?') and len(expr) > 2:
        key = expr[:-2]
        if _KEY_RE.match(key):
            return (key, '!?', '')
    if expr.endswith('?') and not expr.endswith('!?') and len(expr) > 1:
        key = expr[:-1]
        if _KEY_RE.match(key):
            return (key, '?', '')

    raise ValueError(
        f"Cannot parse filter expression {expr!r}: "
        f"no recognized operator found. "
        f"Supported operators: = != ~= !~ ? !?")


def _resolve_filter_key(key: str, record: dict) -> tuple[str, bool]:
    """Resolve a filter key to its value in a subdataset record.

    Parameters
    ----------
    key : str
        Filter key. Dot-prefixed keys (e.g. ``.state``) look up internal
        properties directly. Bare keys (e.g. ``url``) look up
        ``gitmodule_<key>`` in the record.
    record : dict
        Subdataset record dictionary.

    Returns
    -------
    tuple of (str, bool)
        ``(value_string, found)`` where ``found`` indicates whether the key
        was present in the record.
    """
    if key.startswith('.'):
        # Internal property — strip the dot
        internal_key = key[1:]
        if internal_key in record:
            return (str(record[internal_key]), True)
        return ('', False)
    else:
        # .gitmodules property
        gitmodule_key = f'gitmodule_{key}'
        if gitmodule_key in record:
            return (str(record[gitmodule_key]), True)
        return ('', False)


def match_filter(record: dict, parsed_filter: tuple[str, str, str]) -> bool:
    """Evaluate a single parsed filter against a subdataset record.

    Parameters
    ----------
    record : dict
        Subdataset record dictionary.
    parsed_filter : tuple of (str, str, str)
        ``(key, operator, value)`` as returned by :func:`parse_filter_spec`.

    Returns
    -------
    bool
        Whether the record matches the filter.
    """
    key, op, value = parsed_filter
    resolved_value, found = _resolve_filter_key(key, record)

    if op == '?':
        return found and resolved_value != ''
    if op == '!?':
        return not found or resolved_value == ''

    # For comparison operators, missing key means no match
    if not found:
        return False

    if op == '=':
        return resolved_value == value
    if op == '!=':
        return resolved_value != value
    if op == '~=':
        return re.search(value, resolved_value) is not None
    if op == '!~':
        return re.search(value, resolved_value) is None

    raise ValueError(f"Unknown operator {op!r}")


def match_filters(
        record: dict, parsed_filters: list[tuple[str, str, str]],
) -> bool:
    """Evaluate multiple parsed filters against a subdataset record (AND logic).

    All filters must match for the record to pass. An empty filter list
    matches everything.

    Parameters
    ----------
    record : dict
        Subdataset record dictionary.
    parsed_filters : list of tuple
        List of ``(key, operator, value)`` tuples as returned by
        :func:`parse_filter_spec`.

    Returns
    -------
    bool
        Whether the record matches all filters.
    """
    # TODO: consider OR logic in the future — users can use regex alternation
    # within a single filter for now: url~=(pattern1|pattern2)
    return all(match_filter(record, f) for f in parsed_filters)


def _get_gitmodules_filter_map(repo) -> dict:
    """Return a map of submodule paths to gitmodule properties.

    Results are cached on the repo object to avoid re-parsing
    ``.gitmodules`` on every subdataset encountered during recursion.

    Parameters
    ----------
    repo : GitRepo
        Repository whose ``.gitmodules`` to parse.

    Returns
    -------
    dict
        ``{PurePosixPath: {str: str}}`` — keys are repo-relative submodule
        paths, values are dicts with ``gitmodule_*`` properties.
    """
    cache_attr = '_datalad_gitmodules_filter_cache'
    cached = getattr(repo, cache_attr, None)
    if cached is not None:
        return cached
    result = repo._parse_gitmodules()
    setattr(repo, cache_attr, result)
    return result


def match_submodule_filter(
        repo, ds_pathobj, submod_path, props: dict,
        parsed_filters: list[tuple[str, str, str]],
) -> bool:
    """Check if a subdataset passes the recursion filter.

    Used by the diff/status recursion path where ``.gitmodules``
    properties are not directly available.  Looks them up via
    :func:`_get_gitmodules_filter_map` and builds a record compatible
    with :func:`match_filters`.

    Parameters
    ----------
    repo : GitRepo
        Repository containing the submodule.
    ds_pathobj : Path
        Absolute path of the parent dataset.
    submod_path : Path
        Absolute path of the submodule entry (as reported by diffstatus).
    props : dict
        diffstatus properties (has 'type', 'state', 'gitshasum').
    parsed_filters : list
        Parsed filter specs from :func:`parse_filter_spec`.

    Returns
    -------
    bool
        True if the submodule passes all filters (should recurse into).
    """
    from pathlib import PurePosixPath

    if not parsed_filters:
        return True
    gitmodules = _get_gitmodules_filter_map(repo)
    # submod_path is absolute; convert to repo-relative PurePosixPath
    rel_path = PurePosixPath(submod_path.relative_to(repo.pathobj))
    sm_record = dict(gitmodules.get(rel_path, {}))
    # add internal properties that filters can reference via dot-prefix
    sm_record['path'] = ds_pathobj / submod_path.relative_to(repo.pathobj)
    if 'state' not in sm_record:
        sm_record['state'] = props.get('state', 'unknown')
    return match_filters(sm_record, parsed_filters)
