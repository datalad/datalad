# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Interface result handling functions

"""

from __future__ import annotations

__docformat__ = 'restructuredtext'

import atexit
import json
import logging
import os
import traceback
from collections import defaultdict
from collections.abc import (
    Iterable,
    Iterator,
    Mapping,
    MutableMapping,
)
from dataclasses import (
    dataclass,
    field,
    fields,
)
from os.path import (
    isabs,
    isdir,
)
from os.path import join as opj
from os.path import (
    normpath,
    relpath,
)
from typing import (
    Any,
    ClassVar,
    Optional,
)

from datalad.distribution.dataset import Dataset
from datalad.support.exceptions import (
    CapturedException,
    CommandError,
    format_oneline_tb,
)
from datalad.support.path import robust_abspath
from datalad.utils import (
    PurePosixPath,
    ensure_list,
    path_is_subpath,
)

lgr = logging.getLogger('datalad.interface.results')
lgr.log(5, "Importing datalad.interface.results")

# which status is a success , which is failure
success_status_map = {
    'ok': 'success',
    'notneeded': 'success',
    'impossible': 'failure',
    'error': 'failure',
}

# Canonical status values per docs/source/design/result_records.rst.
# Used by StatusRecord to validate status assignments in v2.4 strict mode.
_VALID_STATUSES = frozenset(success_status_map)


def _strict_mode_enabled() -> bool:
    """Whether StatusRecord runs in strict mode.

    Controlled by ``DATALAD_STATUSRECORD_STRICT`` environment variable
    (truthy values: ``1``, ``true``, ``yes`` — case-insensitive). Off by
    default so existing producers and extensions are unaffected.
    """
    v = os.environ.get('DATALAD_STATUSRECORD_STRICT', '').strip().lower()
    return v in ('1', 'true', 'yes')


# ---------------------------------------------------------------------------
# v2.6: runtime extras-key telemetry
#
# When ``DATALAD_STATUSRECORD_TRACE=1`` is set in the environment, every
# write of a key into ``StatusRecord._extras`` is recorded with the
# topmost in-tree call site, the producing ``action`` / ``type`` (where
# known on the record at that point), the value's Python type, and a
# few example values. On process exit the accumulated buckets are
# serialised to JSONL at ``DATALAD_STATUSRECORD_TRACE_PATH`` (default
# ``/tmp/datalad_statusrecord_trace.jsonl``).
#
# The output drives the v2.6 promote-or-subclass redo per
# ``docs/designs/status-record.md``: a static grep is structurally
# incomplete (it misses dynamic key construction in addurls, helpers
# that spread ``**res_kwargs`` from closures, etc.); the runtime audit
# replaces it with real data.
#
# When trace is off (the default), the only cost on the hot path is
# one cached-bool check.
# ---------------------------------------------------------------------------

# Frames inside these files are skipped when locating the producer call
# site — they are part of the StatusRecord plumbing, not the producer.
_TRACE_SKIP_FILES = (
    'datalad/interface/results.py',
    'datalad/interface/utils.py',
    # standard library / framework frames are skipped via the
    # 'datalad/' substring check below
)

_TRACE_ENABLED: Optional[bool] = None
_TRACE_BUCKETS: dict = defaultdict(lambda: {
    'count': 0,
    'actions': defaultdict(int),
    'types': defaultdict(int),
    'value_types': defaultdict(int),
    'examples': [],
})


def _trace_enabled() -> bool:
    """Whether runtime extras-key telemetry is on.

    Controlled by ``DATALAD_STATUSRECORD_TRACE`` (truthy: ``1`` /
    ``true`` / ``yes``). The result is cached on first read so the hot
    path stays cheap when off.
    """
    global _TRACE_ENABLED
    if _TRACE_ENABLED is None:
        v = os.environ.get(
            'DATALAD_STATUSRECORD_TRACE', '').strip().lower()
        _TRACE_ENABLED = v in ('1', 'true', 'yes')
    return _TRACE_ENABLED


def _trace_reset() -> None:
    """Clear cached enabled-state and accumulated buckets.

    Test-only helper; resets module state between sweeps so unit tests
    can drive the env var with ``monkeypatch``.
    """
    global _TRACE_ENABLED
    _TRACE_ENABLED = None
    _TRACE_BUCKETS.clear()


def _trace_top_frame() -> str:
    """Find the topmost in-tree call site, skipping plumbing frames.

    Walks the stack from innermost to outermost and returns the
    deepest frame inside ``datalad/`` that is *not* part of the
    StatusRecord plumbing. Returned as ``"datalad/...:lineno"`` so it
    groups well in the JSONL output. Returns ``<no-in-tree-caller>``
    if the call stack contains no datalad/ producer frame (synthetic
    REPL invocations, third-party callers, etc.).
    """
    for frame in reversed(traceback.extract_stack()):
        path = frame.filename
        if 'datalad/' not in path:
            continue
        if any(skip in path for skip in _TRACE_SKIP_FILES):
            continue
        idx = path.rfind('datalad/')
        return f"{path[idx:]}:{frame.lineno}"
    return '<no-in-tree-caller>'


def _trace_record_extra(
    key: str,
    value: Any,
    action: Any,
    type_: Any,
) -> None:
    """Record a single extras-key write. No-op when trace is off."""
    if not _trace_enabled():
        return
    frame = _trace_top_frame()
    bucket = _TRACE_BUCKETS[(key, frame)]
    bucket['count'] += 1
    if action is not None and action is not _UNSET:
        bucket['actions'][str(action)] += 1
    if type_ is not None and type_ is not _UNSET:
        bucket['types'][str(type_)] += 1
    bucket['value_types'][type(value).__name__] += 1
    if len(bucket['examples']) < 3:
        try:
            bucket['examples'].append(repr(value)[:200])
        except Exception:
            pass


def _trace_dump() -> None:
    """Serialise accumulated extras-key buckets to JSONL.

    Runs at process exit via ``atexit``. Also callable explicitly for
    test harnesses. No-op when trace is off or no records were
    captured. Output path is ``DATALAD_STATUSRECORD_TRACE_PATH`` or
    ``/tmp/datalad_statusrecord_trace.jsonl``.
    """
    if not _trace_enabled() or not _TRACE_BUCKETS:
        return
    path = os.environ.get(
        'DATALAD_STATUSRECORD_TRACE_PATH',
        '/tmp/datalad_statusrecord_trace.jsonl')
    try:
        with open(path, 'w') as f:
            for (key, frame), bucket in sorted(_TRACE_BUCKETS.items()):
                rec = {
                    'key': key,
                    'frame': frame,
                    'count': bucket['count'],
                    'actions': dict(bucket['actions']),
                    'types': dict(bucket['types']),
                    'value_types': dict(bucket['value_types']),
                    'examples': bucket['examples'],
                }
                f.write(json.dumps(rec) + '\n')
        # also leave a hint in the log so humans notice the file
        lgr.info(
            'StatusRecord extras-key telemetry written to %s '
            '(%d distinct (key, frame) clusters)',
            path, len(_TRACE_BUCKETS))
    except Exception as exc:
        # best-effort; do not break process exit on telemetry I/O
        lgr.debug(
            'StatusRecord telemetry dump failed: %s', exc)


atexit.register(_trace_dump)


# ---------------------------------------------------------------------------
# StatusRecord: typed result record that also implements MutableMapping
#
# Designed to be a drop-in replacement for the plain dict that
# ``get_status_dict()`` historically returned. The class declares the
# documented result-record fields (see ``docs/source/design/result_records.rst``)
# as typed attributes, while any unknown / domain-specific keys are stored in
# an internal ``_extras`` mapping so that:
#
#   * existing dict-style consumers (``r['k']``, ``r.get('k')``, ``'k' in r``,
#     ``r['k'] = v``, ``dict(r)``, ``r.items()``, JSON serialization, hook
#     match, pickling, etc.) keep working unchanged;
#   * new code may use typed attribute access (``r.status``, ``r.path``);
#   * the visible "key set" mirrors the old dict: a declared field is only
#     reported as present when it has been explicitly set to a non-None value.
#
# See ``docs/designs/status-record.md`` for the migration plan.
# ---------------------------------------------------------------------------

# A sentinel to distinguish "field never set" from "explicitly set to None".
# Plain ``None`` is a valid value for several fields (``message`` etc.) so we
# need an unambiguous unset marker for declared fields. The marker is hidden
# from external consumers: __getitem__/__contains__/__iter__ treat _UNSET as
# "absent", and __setitem__ writing _UNSET routes through __delitem__.
_UNSET: Any = object()


@dataclass(eq=False)
class StatusRecord(MutableMapping):
    """Typed DataLad result record.

    Behaves as both a dataclass (typed attribute access for declared fields)
    and a :class:`MutableMapping` (dict-style access for backward
    compatibility). Unknown / domain-specific keys are stored in an internal
    extras mapping and are spliced into the Mapping view transparently.

    Examples
    --------
    >>> r = StatusRecord(action='get', path='/x', status='ok')
    >>> r['status']
    'ok'
    >>> r.status
    'ok'
    >>> 'status' in r
    True
    >>> r['custom'] = 42         # routed into extras
    >>> r['custom']
    42
    >>> sorted(r.keys())
    ['action', 'custom', 'path', 'status']
    """

    # --- documented result-record fields ---
    # All default to a sentinel so that, just like the legacy dict, a field
    # is only "present" once explicitly assigned a non-_UNSET value. The
    # public type of each field is documented in
    # ``docs/source/design/result_records.rst``; the runtime annotations stay
    # ``Any`` to keep this minimal-diff and avoid forcing strict types on
    # existing call sites that pass ``None`` etc.
    #
    # Mandatory and common optional fields:
    action: Any = _UNSET
    path: Any = _UNSET
    status: Any = _UNSET
    type: Any = _UNSET
    message: Any = _UNSET
    logger: Any = _UNSET
    refds: Any = _UNSET
    parentds: Any = _UNSET
    state: Any = _UNSET
    error_message: Any = _UNSET
    exception: Any = _UNSET
    exception_traceback: Any = _UNSET
    exit_code: Any = _UNSET
    # Cross-type fields confirmed by the v2.6 sweep (and grep in
    # gitrepo.py) to apply to both ``type='dataset'`` and
    # ``type='file'`` records — they remain on the base class.
    gitshasum: Any = _UNSET         # SHA1 of the entity
    prev_gitshasum: Any = _UNSET    # SHA1 of a previous state

    # --- escape hatch for arbitrary action-specific keys ---
    _extras: dict = field(default_factory=dict, repr=False)

    # Declared field names in declaration order, plus a frozenset for O(1)
    # membership tests. Computed once per class in __init_subclass__ / via
    # the bootstrap below the class body for the base class. ClassVar keeps
    # @dataclass from treating these as instance fields.
    _DECLARED_FIELDS: ClassVar[tuple] = ()
    _DECLARED_FIELDS_SET: ClassVar[frozenset] = frozenset()

    # Subclasses must call ``_bootstrap_declared_fields(cls)`` after the
    # ``@dataclass`` decorator runs (see helper defined below the class).
    # ``__init_subclass__`` cannot do this for us because it fires before
    # ``@dataclass`` has processed the subclass body.

    def __post_init__(self) -> None:
        # v2.6 telemetry: record any pre-loaded extras at construction time
        # so we capture from_kwargs / direct ``StatusRecord(_extras=...)``
        # call paths in addition to post-construction __setitem__ paths.
        if self._extras and _trace_enabled():
            action = getattr(self, 'action', _UNSET)
            type_ = getattr(self, 'type', _UNSET)
            for k, v in self._extras.items():
                _trace_record_extra(k, v, action, type_)

    # ---- permissive construction from arbitrary kwargs -----------------
    @classmethod
    def from_kwargs(
        cls,
        _mapping: Optional[Mapping] = None,
        /,
        **kwargs: Any,
    ) -> 'StatusRecord':
        """Construct from a mapping and/or arbitrary keyword arguments.

        Mirrors :func:`dict` merge semantics: a positional mapping
        provides the base, and keyword arguments override matching keys.
        Unknown keys are routed into ``_extras``. Used by producers that
        spread an existing result-kwargs dict and add or override fields,
        e.g.::

            yield StatusRecord.from_kwargs(res_kwargs, status='ok')

        For the kwargs-only case (no base mapping), simply omit the
        positional argument::

            yield StatusRecord.from_kwargs(action='get', custom='v')
        """
        merged = dict(_mapping) if _mapping is not None else {}
        merged.update(kwargs)
        declared = {k: v for k, v in merged.items()
                    if k in cls._DECLARED_FIELDS_SET}
        extras = {k: v for k, v in merged.items()
                  if k not in cls._DECLARED_FIELDS_SET}
        return cls(**declared, _extras=extras)

    # ---- MutableMapping protocol ------------------------------------
    def __getitem__(self, key: str) -> Any:
        if key in self._DECLARED_FIELDS_SET:
            v = getattr(self, key)
            if v is _UNSET:
                raise KeyError(key)
            return v
        return self._extras[key]

    def __setitem__(self, key: str, value: Any) -> None:
        if value is _UNSET:
            # treat as deletion to keep "_UNSET means absent" invariant
            try:
                del self[key]
            except KeyError:
                pass
            return
        # v2.4 opt-in unknown-key warning. Off by default so existing
        # producers and extensions are unaffected. Enable via
        # DATALAD_STATUSRECORD_STRICT=1. Status-value validation is in
        # __setattr__ so it catches both dict-style and dataclass-init
        # paths.
        if key not in self._DECLARED_FIELDS_SET:
            if _strict_mode_enabled():
                lgr.warning(
                    "StatusRecord: unknown key %r assigned to extras "
                    "(strict mode is on)", key)
            # v2.6 telemetry: record post-construction extras writes.
            # No-op when DATALAD_STATUSRECORD_TRACE is off.
            _trace_record_extra(
                key, value,
                getattr(self, 'action', _UNSET),
                getattr(self, 'type', _UNSET))
        if key in self._DECLARED_FIELDS_SET:
            setattr(self, key, value)
        else:
            self._extras[key] = value

    def __setattr__(self, name: str, value: Any) -> None:
        # v2.4 opt-in status-value validation. Catches both
        # ``StatusRecord(status=v)`` (auto-generated dataclass __init__
        # routes through __setattr__) and ``r.status = v`` and
        # ``r['status'] = v`` (which calls setattr on declared fields).
        if name == 'status' \
                and value is not _UNSET \
                and value is not None \
                and value not in _VALID_STATUSES \
                and _strict_mode_enabled():
            raise ValueError(
                f"invalid status value {value!r}; "
                f"expected one of {sorted(_VALID_STATUSES)}")
        super().__setattr__(name, value)

    def __delitem__(self, key: str) -> None:
        if key in self._DECLARED_FIELDS_SET:
            if getattr(self, key) is _UNSET:
                raise KeyError(key)
            setattr(self, key, _UNSET)
        else:
            del self._extras[key]

    def __iter__(self) -> Iterator[str]:
        for name in self._DECLARED_FIELDS:
            if getattr(self, name) is not _UNSET:
                yield name
        yield from self._extras

    def __len__(self) -> int:
        n = sum(1 for f in self._DECLARED_FIELDS
                if getattr(self, f) is not _UNSET)
        return n + len(self._extras)

    def __contains__(self, key: object) -> bool:
        if not isinstance(key, str):
            return False
        if key in self._DECLARED_FIELDS_SET:
            return getattr(self, key) is not _UNSET
        return key in self._extras

    def copy(self) -> 'StatusRecord':
        """Return a shallow copy as a fresh ``StatusRecord`` (or subclass).

        Mirrors ``dict.copy()`` for backward compatibility with code that
        treats result records as dicts (e.g. test helpers like
        ``_without_command`` in ``test_foreach_dataset.py`` that mutate
        a copy of each result). The result is a new instance of the same
        concrete class — ``FileStatusRecord.copy()`` returns a
        ``FileStatusRecord`` — and ``_extras`` is also shallow-copied so
        in-place mutation on the copy does not leak back.
        """
        return type(self).from_kwargs(self)

    # ---- equality with dict and other StatusRecord ------------------
    def __eq__(self, other: object) -> bool:
        if isinstance(other, StatusRecord):
            return dict(self) == dict(other)
        if isinstance(other, dict):
            return dict(self) == other
        return NotImplemented

    def __ne__(self, other: object) -> bool:
        result = self.__eq__(other)
        if result is NotImplemented:
            return result
        return not result

    # explicit __hash__ disabled (Mapping-style equality is mutation-sensitive)
    __hash__ = None  # type: ignore[assignment]

    # ---- pickling ---------------------------------------------------
    # Default dataclass pickling round-trips ``__dict__`` verbatim, but the
    # _UNSET sentinel does not survive identity comparison after unpickling
    # (``object()`` instances become fresh objects). Round-trip via the
    # public Mapping view instead.
    def __getstate__(self) -> dict:
        return dict(self)

    def __setstate__(self, state: dict) -> None:
        for name in self._DECLARED_FIELDS:
            object.__setattr__(self, name, _UNSET)
        object.__setattr__(self, '_extras', {})
        for k, v in state.items():
            self[k] = v

    # ---- repr / debugging -------------------------------------------
    def __repr__(self) -> str:
        # mirror plain dict repr so log output etc. doesn't change shape
        return f'{type(self).__name__}({dict(self)!r})'


def _bootstrap_declared_fields(cls: 'type[StatusRecord]') -> None:
    """Refresh ``_DECLARED_FIELDS`` / ``_DECLARED_FIELDS_SET`` on a
    ``StatusRecord`` subclass after the ``@dataclass`` decorator has
    applied.

    ``__init_subclass__`` runs during class creation — before the
    ``@dataclass`` decorator has processed the subclass body — so it
    only sees inherited fields. Subclasses must re-bootstrap after the
    decorator runs. The base class is bootstrapped manually below; new
    subclasses defined elsewhere should call this helper after
    ``@dataclass``.
    """
    cls._DECLARED_FIELDS = tuple(
        f.name for f in fields(cls) if not f.name.startswith('_')
    )
    cls._DECLARED_FIELDS_SET = frozenset(cls._DECLARED_FIELDS)


# bootstrap _DECLARED_FIELDS on the base class itself.
_bootstrap_declared_fields(StatusRecord)


# ---------------------------------------------------------------------------
# Specialised subclasses introduced in v2.6 per the runtime extras-key
# telemetry sweep (see ``docs/designs/status-record.md`` v2.6 outcome and
# ``.git-meta/v26_report.md``). Each subclass extends the base with fields
# that the data showed clustering tightly with a specific entity type.
#
# Subclasses are purely additive; the base ``StatusRecord`` is unchanged
# semantically — extras flow through the same Mapping API regardless.
# Producers opt in by constructing the subclass directly (or via
# ``FileStatusRecord.from_kwargs(...)`` etc.). Consumers do not need to
# change: ``isinstance(r, StatusRecord)`` is True for any subclass and
# the Mapping contract is preserved.
# ---------------------------------------------------------------------------


@dataclass(eq=False)
class FileStatusRecord(StatusRecord):
    """Result record for file / symlink entities.

    Adds typed fields that the v2.6 runtime audit showed concentrate on
    ``type='file'`` results and appear at ≥2 distinct in-tree call sites.
    Most of these come from ``GitRepo.status()`` /
    ``get_content_annexinfo()`` and ``annexjson2result()``.

    File-specific fields previously declared on the base class
    (``bytesize``, ``key`` — promoted in v1+v2.3 from a static grep)
    have been moved here in v2.6 because the runtime data confirmed
    they are strictly file-scoped.
    """

    # Moved from base in v2.6 — runtime audit confirmed file-only use.
    bytesize: Any = _UNSET            # entity size in bytes (int)
    key: Any = _UNSET                 # git-annex key (canonical name)

    # Promoted in v2.6 from extras based on the sweep
    # (see .git-meta/v26_report.md):
    annexkey: Any = _UNSET            # 9 frames, 213 occurrences — alt
                                      # name for ``key``; kept distinct
                                      # because producers populate them
                                      # via different code paths
    backend: Any = _UNSET             # 2 frames, 22 occ
    has_content: Any = _UNSET         # 2 frames, 18 occ
    hashdirlower: Any = _UNSET        # 2 frames,  4 occ
    hashdirmixed: Any = _UNSET        # 2 frames,  4 occ
    humansize: Any = _UNSET           # 2 frames, 22 occ
    keyname: Any = _UNSET             # 2 frames, 22 occ
    mtime: Any = _UNSET               # 2 frames, 22 occ
    objloc: Any = _UNSET              # 2 frames, 18 occ


@dataclass(eq=False)
class SiblingStatusRecord(StatusRecord):
    """Result record for sibling / git-remote entities.

    Adds the canonical sibling name. The remaining sibling-specific
    keys observed in the v2.6 sweep are either hyphenated git-config
    style identifiers (``annex-uuid``, ``annex-ignore``, ``annex-*``,
    ``datalad-publish-depends``) — which cannot be Python attributes
    and therefore must stay in ``_extras`` — or single-call-site
    fields that fail the ≥2 promotion rule. ``url`` is kept in extras
    for now (single call site at sweep time); promote in a future PR
    if a second producer adds it.
    """

    name: Any = _UNSET                # 8 frames, 120 occ


# refresh declared-fields cache on each subclass now that @dataclass has run
_bootstrap_declared_fields(FileStatusRecord)
_bootstrap_declared_fields(SiblingStatusRecord)


def as_status_record(res: Mapping) -> 'StatusRecord':
    """Coerce a result record to a :class:`StatusRecord`.

    Returns ``res`` unchanged if it is already a ``StatusRecord``;
    otherwise wraps the mapping in a fresh ``StatusRecord`` so downstream
    code can rely on typed attribute access. Used at the central pipeline
    entry (``_process_results``) so the in-pipeline result type is
    guaranteed regardless of what a producer yielded.

    The wrapping is shallow: keys flow through ``from_kwargs``, so unknown
    keys land in ``_extras``. The original mapping is not mutated.
    """
    if isinstance(res, StatusRecord):
        return res
    return StatusRecord.from_kwargs(res)


def get_status_dict(
    action: Optional[str] = None,
    ds: Optional[Dataset] = None,
    path: Optional[str] = None,
    type: Optional[str] = None,
    logger: Optional[logging.Logger] = None,
    refds: Optional[str] = None,
    status: Optional[str] = None,
    message: str | tuple | None = None,
    exception: Exception | CapturedException | None = None,
    error_message: str | tuple | None = None,
    **kwargs: Any,
) -> StatusRecord:
    # `type` is intentionally not `type_` or something else, as a mismatch
    # with the dict key 'type' causes too much pain all over the place
    # just for not shadowing the builtin `type` in this function
    """Helper to create a result record.

    Most arguments match their key in the resulting record, and their given
    values are simply assigned to the record under these keys.  Only
    exceptions are listed here.

    Parameters
    ----------
    ds
      If given, the `path` and `type` values are populated with the path of the
      datasets and 'dataset' as the type. Giving additional values for both
      keys will overwrite these pre-populated values.
    exception
      Exceptions that occurred while generating a result should be captured
      by immediately instantiating a CapturedException. This instance can
      be passed here to yield more comprehensive error reporting, including
      an auto-generated traceback (added to the result record under an
      'exception_traceback' key). Exceptions of other types are also supported.

    Returns
    -------
    StatusRecord
        A record that behaves like a dict for backward-compatible
        consumers (subscription, ``.get()``, ``in``, iteration, JSON
        serialization, etc.) and exposes typed attributes for the
        documented fields.
    """

    d: StatusRecord = StatusRecord()
    if action is not None:
        d['action'] = action
    if ds:
        d['path'] = ds.path
        d['type'] = 'dataset'
    # now overwrite automatic
    if path is not None:
        d['path'] = path
    if type:
        d['type'] = type
    if logger:
        d['logger'] = logger
    if refds:
        d['refds'] = refds
    if status is not None:
        # TODO check for known status label
        d['status'] = status
    if message is not None:
        d['message'] = message
    if error_message is not None:
        d['error_message'] = error_message
    if exception is not None:
        d['exception'] = exception
        d['exception_traceback'] = exception.format_oneline_tb(
            include_str=False) \
            if isinstance(exception, CapturedException) \
            else format_oneline_tb(
                exception, include_str=False)
        if error_message is None and isinstance(exception, CapturedException):
            d['error_message'] = exception.message
        if isinstance(exception, CommandError):
            d['exit_code'] = exception.code
    if kwargs:
        d.update(kwargs)
    return d


def results_from_paths(
    paths: str | list[str],
    action: Optional[str] = None,
    type: Optional[str] = None,
    logger: Optional[logging.Logger] = None,
    refds: Optional[str]=None,
    status: Optional[str] = None,
    message: Optional[str] = None,
    exception: Exception | CapturedException | None = None,
) -> Iterator[StatusRecord]:
    """
    Helper to yield analog result dicts for each path in a sequence.

    Parameters
    ----------
    message: str
      A result message. May contain `%s` which will be replaced by the
      respective `path`.

    Returns
    -------
    generator

    """
    for p in ensure_list(paths):
        yield get_status_dict(
            action, path=p, type=type, logger=logger, refds=refds,
            status=status, message=(message, p) if message is not None and '%s' in message else message,
            exception=exception
        )


def is_ok_dataset(r: Mapping) -> bool:
    """Convenience test for a non-failure dataset-related result record.

    Accepts both :class:`StatusRecord` and plain ``dict`` (e.g. results
    yielded from extensions that have not migrated yet).
    """
    return r.get('status', None) == 'ok' and r.get('type', None) == 'dataset'


class ResultXFM:
    """Abstract definition of the result transformer API"""

    def __call__(self, res: Mapping) -> Any:
        """This is called with one result record at a time.

        ``res`` is a :class:`Mapping` — ``StatusRecord`` is supported as
        the typed common case, but plain ``dict`` is also valid.
        """
        raise NotImplementedError


class YieldDatasets(ResultXFM):
    """Result transformer to return a Dataset instance from matching result.

    If the `success_only` flag is given only dataset with 'ok' or 'notneeded'
    status are returned'.

    `None` is returned for any other result.
    """
    def __init__(self, success_only: bool = False) -> None:
        self.success_only = success_only

    def __call__(self, res: Mapping) -> Optional[Dataset]:
        if res.get('type', None) == 'dataset':
            if not self.success_only or \
                    res.get('status', None) in ('ok', 'notneeded'):
                return Dataset(res['path'])
            else:
                return None
        else:
            lgr.debug('rejected by return value configuration: %s', res)
            return None


class YieldRelativePaths(ResultXFM):
    """Result transformer to return relative paths for a result

    Relative paths are determined from the 'refds' value in the result. If
    no such value is found, `None` is returned.
    """
    def __call__(self, res: Mapping) -> Optional[str]:
        refpath = res.get('refds', None)
        if refpath:
            return relpath(res['path'], start=refpath)
        else:
            return None


class YieldField(ResultXFM):
    """Result transformer to return an arbitrary value from a result dict"""
    def __init__(self, field: str) -> None:
        """
        Parameters
        ----------
        field : str
          Key of the field to return.
        """
        self.field = field

    def __call__(self, res: Mapping) -> Any:
        if self.field in res:
            return res[self.field]
        else:
            lgr.debug('rejected by return value configuration: %s', res)
            return None


# a bunch of convenience labels for common result transformers
# the API `result_xfm` argument understand any of these labels and
# applied the corresponding callable
known_result_xfms = {
    'datasets': YieldDatasets(),
    'successdatasets-or-none': YieldDatasets(success_only=True),
    'paths': YieldField('path'),
    'relpaths': YieldRelativePaths(),
    'metadata': YieldField('metadata'),
}

translate_annex_notes = {
    '(Use --force to override this check, or adjust numcopies.)':
        'configured minimum number of copies not found',
}


def annexjson2result(d: dict[str, Any], ds: Dataset, **kwargs: Any) -> StatusRecord:
    """Helper to convert an annex JSON result to a datalad result record

    Info from annex is rather heterogeneous, partly because some of it
    our support functions are faking.

    This helper should be extended with all needed special cases to
    homogenize the information.

    Parameters
    ----------
    d : dict
      Annex info dict.
    ds : Dataset instance
      Used to determine absolute paths for `file` results. This dataset
      is not used to set `refds` in the result, pass this as a separate
      kwarg if needed.
    **kwargs
      Passes as-is to `get_status_dict`. Must not contain `refds`.
    """
    lgr.debug('received JSON result from annex: %s', d)
    messages = []
    res = get_status_dict(**kwargs)
    res['status'] = 'ok' if d.get('success', False) is True else 'error'
    # we cannot rely on any of these to be available as the feed from
    # git annex (or its wrapper) is not always homogeneous
    if d.get('file'):
        res['path'] = str(ds.pathobj / PurePosixPath(d['file']))
    if 'command' in d:
        res['action'] = d['command']
    if 'key' in d:
        res['annexkey'] = d['key']
    if 'fields' in d:
        # this is annex metadata, filter out timestamps
        res['metadata'] = {k: v[0] if isinstance(v, list) and len(v) == 1 else v
                           for k, v in d['fields'].items()
                           if not k.endswith('lastchanged')}
    if d.get('error-messages', None):
        res['error_message'] = '\n'.join(m.strip() for m in d['error-messages'])
    # avoid meaningless standard messages, and collision with actual error
    # messages
    elif 'note' in d:
        note = "; ".join(ln for ln in d['note'].splitlines()
                         if ln != 'checksum...'
                         and not ln.startswith('checking file'))
        if note:
            messages.append(translate_annex_notes.get(note, note))
    if messages:
        res['message'] = '\n'.join(m.strip() for m in messages)
    return res


def count_results(res: Iterable[Mapping], **kwargs: Any) -> int:
    """Return number of results that match all property values in kwargs"""
    return sum(
        all(k in r and r[k] == v for k, v in kwargs.items()) for r in res)


def only_matching_paths(res: Mapping, **kwargs: Any) -> bool:
    # TODO handle relative paths by using a contained 'refds' value
    paths = ensure_list(kwargs.get('path', []))
    respath = res.get('path', None)
    return respath in paths


# needs decorator, as it will otherwise bind to the command classes that use it
@staticmethod  # type: ignore[misc]
def is_result_matching_pathsource_argument(res: Mapping, **kwargs: Any) -> bool:
    # we either have any non-zero number of "paths" (that could be anything), or
    # we have one path and one source
    # we don't do any error checking here, done by the command itself
    if res.get('action', None) not in ('install', 'get'):
        # this filter is only used in install, reject anything that comes
        # in that could not possibly be a 'install'-like result
        # e.g. a sibling being added in the process
        return False
    source = kwargs.get('source', None)
    if source is not None:
        # we want to be able to deal with Dataset instances given as 'source':
        if isinstance(source, Dataset):
            source = source.path
        # if there was a source, it needs to be recorded in the result
        # otherwise this is not what we are looking for
        return source == res.get('source_url', None)
    # the only thing left is a potentially heterogeneous list of paths/URLs
    paths = ensure_list(kwargs.get('path', []))
    # three cases left:
    # 1. input arg was an absolute path -> must match 'path' property
    # 2. input arg was relative to a dataset -> must match refds/relpath
    # 3. something nifti with a relative input path that uses PWD as the
    #    reference
    respath = res.get('path', None)
    if respath in paths:
        # absolute match, pretty sure we want this
        return True
    elif isinstance(kwargs.get('dataset', None), Dataset) and \
            YieldRelativePaths()(res) in paths:
        # command was called with a reference dataset, and a relative
        # path of a result matches in input argument -- not 100% exhaustive
        # test, but could be good enough
        return True
    elif any(robust_abspath(p) == respath for p in paths):
        # one absolutified input path matches the result path
        # I'd say: got for it!
        return True
    elif any(p == res.get('source_url', None) for p in paths):
        # this was installed from a URL that was given, we'll take that too
        return True
    else:
        return False


def results_from_annex_noinfo(
    ds: Dataset,
    requested_paths: list[str],
    respath_by_status: dict[str, list[str]],
    dir_fail_msg: str,
    noinfo_dir_msg: str,
    noinfo_file_msg: str,
    noinfo_status: str = 'notneeded',
    **kwargs: Any
) -> Iterator[StatusRecord]:
    """Helper to yield results based on what information git annex did no give us.

    The helper assumes that the annex command returned without an error code,
    and interprets which of the requested paths we have heard nothing about,
    and assumes that git annex was happy with their current state.

    Parameters
    ==========
    ds : Dataset
      All results have to be concerning this single dataset (used to resolve
      relpaths).
    requested_paths : list
      List of path arguments sent to `git annex`
    respath_by_status : dict
      Mapping of 'success' or 'failure' labels to lists of result paths
      reported by `git annex`. Everything that is not in here, we assume
      that `git annex` was happy about.
    dir_fail_msg : str
      Message template to inject into the result for a requested directory where
      a failure was reported for some of its content. The template contains two
      string placeholders that will be expanded with 1) the path of the
      directory, and 2) the content failure paths for that directory
    noinfo_dir_msg : str
      Message template to inject into the result for a requested directory that
      `git annex` was silent about (incl. any content). There must be one string
      placeholder that is expanded with the path of that directory.
    noinfo_file_msg : str
      Message to inject into the result for a requested file that `git
      annex` was silent about.
    noinfo_status : str
      Status to report when annex provides no information
    **kwargs
      Any further kwargs are included in the yielded result dictionary.
    """
    for p in requested_paths:
        # any relpath is relative to the currently processed dataset
        # not the global reference dataset
        p = p if isabs(p) else normpath(opj(ds.path, p))
        if any(p in ps for ps in respath_by_status.values()):
            # we have a report for this path already
            continue
        common_report = dict(path=p, **kwargs)
        if isdir(p):
            # `annex` itself will not report on directories, but if a
            # directory was requested, we want to say something about
            # it in the results.  we are inside a single, existing
            # repo, hence all directories are already present, if not
            # we had an error
            # do we have any failures in a subdir of the requested dir?
            failure_results = [
                fp for fp in respath_by_status.get('failure', [])
                if path_is_subpath(fp, p)]
            if failure_results:
                # we were not able to process all requested_paths, let's label
                # this 'impossible' to get a warning-type report
                # after all we have the directory itself, but not
                # (some) of its requested_paths
                yield get_status_dict(
                    status='impossible', type='directory',
                    message=(dir_fail_msg, p, failure_results),
                    **common_report)
            else:
                # otherwise cool, but how cool?
                success_results = [
                    fp for fp in respath_by_status.get('success', [])
                    if path_is_subpath(fp, p)]
                yield get_status_dict(
                    status='ok' if success_results else noinfo_status,
                    message=None if success_results else (noinfo_dir_msg, p),
                    type='directory', **common_report)
            continue
        else:
            # not a directory, and we have had no word from `git annex`,
            # yet no exception, hence the file was most probably
            # already in the desired state
            yield get_status_dict(
                status=noinfo_status, type='file',
                message=noinfo_file_msg,
                **common_report)


lgr.log(5, "Done importing datalad.interface.results")
