# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Tests for ``StatusRecord`` and its dict-compatibility surface.

The migration from plain ``dict`` to ``StatusRecord`` (see
``docs/designs/status-record.md``) must preserve every dict-shaped consumer
pattern in the codebase: subscription, ``.get()`` / ``in`` / iteration,
mutation, ``.pop()``, dict-spreading, JSON serialization, equality with plain
dicts, hook-style key matching, and pickling.

These tests pin those invariants so we can refactor producers and central
consumers in v2 without silent regressions.
"""

import json
import logging
import pickle

import pytest

from datalad.interface.results import (
    _TRACE_BUCKETS,
    _UNSET,
    StatusRecord,
    _trace_dump,
    _trace_enabled,
    _trace_record_extra,
    _trace_reset,
    get_status_dict,
)


# Reference implementation: the old dict-building body of get_status_dict,
# without the StatusRecord wrapper. Used as the equivalence oracle in tests
# that must stay byte-identical with the legacy behavior.
def _legacy_get_status_dict(action=None, ds=None, path=None, type=None,
                            logger=None, refds=None, status=None,
                            message=None, error_message=None, **kwargs):
    d = {}
    if action is not None:
        d['action'] = action
    if ds:
        d['path'] = ds.path
        d['type'] = 'dataset'
    if path is not None:
        d['path'] = path
    if type:
        d['type'] = type
    if logger:
        d['logger'] = logger
    if refds:
        d['refds'] = refds
    if status is not None:
        d['status'] = status
    if message is not None:
        d['message'] = message
    if error_message is not None:
        d['error_message'] = error_message
    if kwargs:
        d.update(kwargs)
    return d


# ---------------------------------------------------------------------------
# basic construction and Mapping protocol
# ---------------------------------------------------------------------------

def test_construction_empty():
    r = StatusRecord()
    assert len(r) == 0
    assert list(r) == []
    assert dict(r) == {}


def test_construction_via_kwargs_for_declared_fields():
    r = StatusRecord(action='get', path='/x', status='ok')
    assert r['action'] == 'get'
    assert r['path'] == '/x'
    assert r['status'] == 'ok'
    assert r.action == 'get'
    assert r.path == '/x'
    assert r.status == 'ok'


def test_init_rejects_unknown_kwargs():
    """Typed ``__init__`` is strict — unknown kwargs raise TypeError.
    Producers that need permissive behavior must use ``from_kwargs``."""
    with pytest.raises(TypeError):
        StatusRecord(action='get', custom='v')   # type: ignore[call-arg]


def test_from_kwargs_routes_unknown_to_extras():
    r = StatusRecord.from_kwargs(action='get', path='/x', status='ok',
                                 custom='v', another=42)
    assert r['action'] == 'get'
    assert r['custom'] == 'v'
    assert r['another'] == 42
    assert r.action == 'get'
    assert sorted(r.keys()) == ['action', 'another', 'custom', 'path', 'status']


def test_from_kwargs_preserves_iteration_order_for_extras():
    """Declared fields come first (in declaration order), extras follow in
    kwargs order. Pin this so producer-side spreads have stable JSON output.
    """
    r = StatusRecord.from_kwargs(
        action='get', custom='1', another='2', status='ok')
    assert list(r) == ['action', 'status', 'custom', 'another']


def test_from_kwargs_empty_works():
    r = StatusRecord.from_kwargs()
    assert len(r) == 0
    assert dict(r) == {}


def test_from_kwargs_positional_mapping_with_overrides():
    """Mirrors ``dict(mapping, **overrides)``: positional mapping is the
    base, kwargs override matching keys. This is the call form used by
    producers that spread an existing res_kwargs dict and need to add or
    override fields (e.g. ``yield StatusRecord.from_kwargs(res_kwargs,
    type=c['type'], path=c['path'], action='copy')``).
    """
    base = {'action': 'publish', 'type': 'dataset', 'custom': 'v'}
    r = StatusRecord.from_kwargs(base, type='file', path='/x')
    assert r['action'] == 'publish'
    assert r['type'] == 'file'           # overridden
    assert r['path'] == '/x'             # added
    assert r['custom'] == 'v'            # extras flow through
    # source mapping is not mutated
    assert base == {'action': 'publish', 'type': 'dataset', 'custom': 'v'}


def test_from_kwargs_positional_only():
    """Positional mapping with no override kwargs works as a pure copy."""
    base = {'action': 'get', 'custom': 'v'}
    r = StatusRecord.from_kwargs(base)
    assert dict(r) == base


def test_from_kwargs_accepts_status_record_as_base():
    """A previously-yielded StatusRecord can serve as the base mapping
    (used by ``status.py`` recursion: ``from_kwargs(r, refds=..., action=...)``).
    """
    r1 = StatusRecord.from_kwargs(action='get', path='/x', custom='v')
    r2 = StatusRecord.from_kwargs(r1, refds='/refds', action='status')
    assert r2['action'] == 'status'      # overridden
    assert r2['refds'] == '/refds'
    assert r2['path'] == '/x'
    assert r2['custom'] == 'v'


def test_unset_field_is_absent():
    r = StatusRecord(action='get')
    assert 'path' not in r
    with pytest.raises(KeyError):
        r['path']
    # but .get() with default works as expected
    assert r.get('path') is None
    assert r.get('path', 'fallback') == 'fallback'


def test_in_operator_only_for_strings():
    r = StatusRecord(action='get')
    assert 'action' in r
    assert 42 not in r            # non-string keys: just absent, no TypeError


def test_set_unknown_key_routes_to_extras():
    r = StatusRecord(action='get')
    r['custom'] = 1
    r['annex-ignore'] = 'false'   # hyphenated key, can't be an attribute
    assert r['custom'] == 1
    assert r['annex-ignore'] == 'false'
    assert 'custom' in r
    assert 'annex-ignore' in r


def test_setitem_for_declared_field_updates_attribute():
    r = StatusRecord()
    r['status'] = 'ok'
    assert r.status == 'ok'
    assert r['status'] == 'ok'


def test_delitem_removes_declared_and_extras():
    r = StatusRecord(action='get')
    r['custom'] = 1
    del r['action']
    assert 'action' not in r
    del r['custom']
    assert 'custom' not in r
    with pytest.raises(KeyError):
        del r['action']            # already absent
    with pytest.raises(KeyError):
        del r['nonexistent']


def test_copy_returns_independent_instance():
    """``StatusRecord.copy()`` mirrors ``dict.copy()`` semantics: a fresh
    instance, mutations on the copy don't leak back. Backward-compat for
    test helpers (``_without_command`` in ``test_foreach_dataset.py``)
    and producer code (``save.py:360``) that treat result records as
    dicts and call ``.copy()``."""
    r = StatusRecord(action='get', path='/x', status='ok')
    r['custom'] = 'v'
    r2 = r.copy()
    # equal but not the same object
    assert r == r2
    assert r is not r2
    assert isinstance(r2, StatusRecord)
    # extras are also shallow-copied — mutating copy doesn't leak
    r2['extra2'] = 'late'
    assert 'extra2' not in r
    r2['status'] = 'error'
    assert r['status'] == 'ok'


def test_copy_preserves_subclass_type():
    """``copy()`` returns the concrete subclass, not the base."""
    from datalad.interface.results import (
        FileStatusRecord,
        SiblingStatusRecord,
    )
    f = FileStatusRecord(action='get', type='file', bytesize=1234)
    fc = f.copy()
    assert isinstance(fc, FileStatusRecord)
    assert fc.bytesize == 1234

    s = SiblingStatusRecord(action='configure-sibling', type='sibling',
                             name='origin')
    sc = s.copy()
    assert isinstance(sc, SiblingStatusRecord)
    assert sc.name == 'origin'


def test_pop_logger_pattern():
    """The renderer pipeline does ``res.pop('logger', None)`` — verify it
    returns the logger and afterwards ``'logger' not in r``.
    """
    lgr = logging.getLogger('test_pop_logger')
    r = StatusRecord(action='get', logger=lgr)
    popped = r.pop('logger', None)
    assert popped is lgr
    assert 'logger' not in r
    # second pop with default returns the default
    assert r.pop('logger', 'gone') == 'gone'


def test_iter_order_is_declared_then_extras():
    r = StatusRecord(action='a', path='/p', status='ok')
    r['custom'] = 1
    r['other'] = 2
    keys = list(r)
    # declared fields appear in declaration order, extras follow in
    # insertion order
    assert keys[:3] == ['action', 'path', 'status']
    assert keys[3:] == ['custom', 'other']


def test_len_counts_only_set_fields():
    r = StatusRecord()
    assert len(r) == 0
    r['action'] = 'get'
    assert len(r) == 1
    r['custom'] = 1
    assert len(r) == 2
    del r['custom']
    assert len(r) == 1


# ---------------------------------------------------------------------------
# equality, dict-spread, items/keys/values
# ---------------------------------------------------------------------------

def test_equality_with_plain_dict():
    r = StatusRecord(action='get', path='/x', status='ok')
    assert r == {'action': 'get', 'path': '/x', 'status': 'ok'}
    assert {'action': 'get', 'path': '/x', 'status': 'ok'} == dict(r)


def test_equality_between_records():
    r1 = StatusRecord(action='get', path='/x', status='ok')
    r2 = StatusRecord(action='get', path='/x', status='ok')
    r3 = StatusRecord(action='get', path='/y', status='ok')
    assert r1 == r2
    assert r1 != r3


def test_equality_includes_extras():
    r1 = StatusRecord(action='get')
    r2 = StatusRecord(action='get')
    r1['custom'] = 1
    assert r1 != r2
    r2['custom'] = 1
    assert r1 == r2


def test_equality_against_non_mapping():
    r = StatusRecord(action='get')
    assert r != 42
    assert r != 'get'
    assert (r == 'get') is False


def test_dict_spread_into_dict():
    r = StatusRecord(action='get', path='/x', status='ok')
    spread = dict(r, message='hi')
    assert spread == {
        'action': 'get', 'path': '/x', 'status': 'ok', 'message': 'hi',
    }


def test_dict_spread_from_dict():
    base = {'action': 'get', 'path': '/x'}
    r = StatusRecord(**base, status='ok')
    assert r == {'action': 'get', 'path': '/x', 'status': 'ok'}


def test_items_keys_values():
    r = StatusRecord(action='get', status='ok')
    r['custom'] = 1
    assert sorted(r.keys()) == ['action', 'custom', 'status']
    assert sorted(r.values(), key=str) == [1, 'get', 'ok']
    assert sorted(r.items()) == [
        ('action', 'get'), ('custom', 1), ('status', 'ok'),
    ]


def test_extras_never_visible_as_a_key():
    r = StatusRecord(action='get')
    r['custom'] = 1
    # the internal _extras dict must not surface as a key in any view
    assert '_extras' not in r
    assert '_extras' not in list(r)
    assert '_extras' not in r.keys()
    assert '_extras' not in dict(r)


# ---------------------------------------------------------------------------
# JSON serialization byte-equivalence with the legacy dict
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('kw', [
    dict(),
    dict(action='get'),
    dict(action='get', path='/x', status='ok'),
    dict(action='get', path='/x', status='ok', message='hello'),
    dict(action='get', path='/x', status='ok', extra_key='extra_value'),
    dict(action='get', path='/x', status='ok',
         message=('formatted %s', 'arg')),
])
def test_json_serialization_matches_legacy(kw):
    r = get_status_dict(**kw)
    legacy = _legacy_get_status_dict(**kw)
    assert json.dumps(dict(r), sort_keys=True, default=str) == \
        json.dumps(legacy, sort_keys=True, default=str)
    # unsorted JSON must also match because iteration order is preserved
    assert json.dumps(dict(r), default=str) == \
        json.dumps(legacy, default=str)


# ---------------------------------------------------------------------------
# get_status_dict equivalence
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('kw', [
    dict(action='get'),
    dict(action='get', path='/x', status='ok'),
    dict(action='get', path='/x', status='ok', message='hello'),
    dict(action='get', path='/x', status='ok',
         message='hello', error_message='boom'),
    dict(action='get', path='/x', custom='value', another='more'),
])
def test_get_status_dict_returns_dict_equivalent(kw):
    r = get_status_dict(**kw)
    legacy = _legacy_get_status_dict(**kw)
    assert isinstance(r, StatusRecord)
    assert r == legacy
    assert dict(r) == legacy
    assert list(r) == list(legacy)


def test_get_status_dict_returns_status_record():
    r = get_status_dict(action='get', status='ok')
    assert isinstance(r, StatusRecord)
    # but still a Mapping
    from collections.abc import Mapping
    assert isinstance(r, Mapping)


# ---------------------------------------------------------------------------
# Mutation patterns observed in the codebase
# ---------------------------------------------------------------------------

def test_mutation_of_status_message_path():
    """update.py / siblings.py / addurls.py mutate these post-construction."""
    r = get_status_dict(action='update', path='/x', status='impossible')
    r['status'] = 'notneeded'
    r['message'] = 'reconsidered'
    r['path'] = '/y'
    assert r['status'] == 'notneeded'
    assert r['message'] == 'reconsidered'
    assert r['path'] == '/y'


def test_mutation_of_extras_key():
    """create_sibling_gin.py: ``res['annex-ignore'] = 'false'``."""
    r = get_status_dict(action='configure-sibling', path='/x', status='ok')
    r['annex-ignore'] = 'false'
    assert r['annex-ignore'] == 'false'
    assert 'annex-ignore' in dict(r)


# ---------------------------------------------------------------------------
# Hook-style key match (datalad/core/local/resulthooks.py)
# ---------------------------------------------------------------------------

def test_jsonhook_match_against_status_record():
    """The hook system iterates ``match.items()`` and checks
    ``k in res`` / ``res[k] == val``. Verify the StatusRecord matches the
    same way as a plain dict.
    """
    from datalad.core.local.resulthooks import match_jsonhook2result
    r = get_status_dict(action='get', path='/x', status='ok', type='file')
    legacy = _legacy_get_status_dict(
        action='get', path='/x', status='ok', type='file')

    matches = [
        # eq operator (default)
        {'action': 'get'},
        {'action': 'get', 'status': 'ok'},
        # in operator
        {'type': ['in', ['file', 'directory']]},
        # neq operator
        {'status': ['neq', 'error']},
    ]
    nonmatches = [
        {'action': 'drop'},
        {'type': ['in', ['dataset']]},
        {'status': ['neq', 'ok']},
    ]
    for m in matches:
        assert match_jsonhook2result('h', r, m) == \
            match_jsonhook2result('h', legacy, m)
        assert match_jsonhook2result('h', r, m) is True
    for m in nonmatches:
        assert match_jsonhook2result('h', r, m) == \
            match_jsonhook2result('h', legacy, m)
        assert match_jsonhook2result('h', r, m) is False


# ---------------------------------------------------------------------------
# EnsureKeyChoice constraint (datalad/support/constraints.py)
# ---------------------------------------------------------------------------

def test_ensure_key_choice_accepts_status_record():
    from datalad.support.constraints import EnsureKeyChoice
    constraint = EnsureKeyChoice('action', ('install', 'get'))
    r = get_status_dict(action='install', path='/x', status='ok')
    assert constraint(r) is r
    bad = get_status_dict(action='drop', path='/x', status='ok')
    with pytest.raises(ValueError):
        constraint(bad)


# ---------------------------------------------------------------------------
# Pickling
# ---------------------------------------------------------------------------

def test_pickle_round_trip():
    r = get_status_dict(action='get', path='/x', status='ok',
                        message='hi', custom='value')
    r2 = pickle.loads(pickle.dumps(r))
    assert isinstance(r2, StatusRecord)
    assert r == r2
    assert dict(r) == dict(r2)


def test_pickle_round_trip_with_logger_removed():
    """Logger isn't picklable in general; the pipeline pops it before
    serialization. Verify the pop+pickle pattern works."""
    lgr = logging.getLogger('test_pickle')
    r = get_status_dict(action='get', path='/x', status='ok', logger=lgr)
    r.pop('logger', None)
    r2 = pickle.loads(pickle.dumps(r))
    assert r == r2
    assert 'logger' not in r2


# ---------------------------------------------------------------------------
# repr / debugging
# ---------------------------------------------------------------------------

def test_repr_shows_dict_view():
    r = StatusRecord(action='get', status='ok')
    s = repr(r)
    assert 'StatusRecord' in s
    assert "'action': 'get'" in s
    assert "'status': 'ok'" in s


# ---------------------------------------------------------------------------
# Sentinel hygiene
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# v2.4: opt-in strict-mode validation
# ---------------------------------------------------------------------------

def test_strict_mode_disabled_by_default(monkeypatch):
    """Strict mode is opt-in: unset env => no validation, anything goes."""
    monkeypatch.delenv('DATALAD_STATUSRECORD_STRICT', raising=False)
    # invalid status accepted via every path
    r = StatusRecord(status='funky')
    assert r.status == 'funky'
    r['status'] = 'wat'
    assert r.status == 'wat'
    # unknown extras key accepted silently
    r['unknown_key'] = 1
    assert r['unknown_key'] == 1


@pytest.mark.parametrize('truthy', ['1', 'true', 'yes', 'TRUE', 'Yes'])
def test_strict_mode_status_validation_via_init(monkeypatch, truthy):
    """Strict mode rejects invalid status values at construction time
    (catches the dataclass __init__ path that __setitem__ does not see)."""
    monkeypatch.setenv('DATALAD_STATUSRECORD_STRICT', truthy)
    with pytest.raises(ValueError, match='invalid status value'):
        StatusRecord(status='funky')
    # canonical statuses still accepted
    for s in ('ok', 'notneeded', 'impossible', 'error'):
        r = StatusRecord(status=s)
        assert r.status == s


def test_strict_mode_status_validation_via_setitem(monkeypatch):
    monkeypatch.setenv('DATALAD_STATUSRECORD_STRICT', '1')
    r = StatusRecord(status='ok')
    with pytest.raises(ValueError, match='invalid status value'):
        r['status'] = 'broken'
    # original value preserved
    assert r.status == 'ok'


def test_strict_mode_status_validation_via_attribute_assign(monkeypatch):
    monkeypatch.setenv('DATALAD_STATUSRECORD_STRICT', '1')
    r = StatusRecord(status='ok')
    with pytest.raises(ValueError, match='invalid status value'):
        r.status = 'oh-no'
    assert r.status == 'ok'


def test_strict_mode_unknown_key_warns(monkeypatch, caplog):
    """Unknown keys still go to _extras in strict mode, but emit a
    WARNING so CI / development surfaces typos.
    """
    import logging as _log
    monkeypatch.setenv('DATALAD_STATUSRECORD_STRICT', '1')
    r = StatusRecord(action='get')
    with caplog.at_level(_log.WARNING, logger='datalad.interface.results'):
        r['typo_key'] = 1
    assert 'typo_key' in r
    assert any('unknown key' in m.message for m in caplog.records), \
        f'expected warning, got: {[m.message for m in caplog.records]}'


def test_strict_mode_status_none_allowed(monkeypatch):
    """``None`` is the legacy "absent" marker (e.g. r['status'] = None
    used to silently drop the key). Strict mode must not treat it as an
    invalid status value.
    """
    monkeypatch.setenv('DATALAD_STATUSRECORD_STRICT', '1')
    r = StatusRecord(status=None)        # accepted
    assert r.status is None


# ---------------------------------------------------------------------------
# v2.6: extras-key telemetry
# ---------------------------------------------------------------------------

@pytest.fixture
def trace_off(monkeypatch):
    monkeypatch.delenv('DATALAD_STATUSRECORD_TRACE', raising=False)
    _trace_reset()
    yield
    _trace_reset()


@pytest.fixture
def trace_on(monkeypatch):
    monkeypatch.setenv('DATALAD_STATUSRECORD_TRACE', '1')
    _trace_reset()
    yield
    _trace_reset()


def test_trace_disabled_by_default(trace_off):
    """No env var → trace is off → no buckets accumulate."""
    assert not _trace_enabled()
    r = StatusRecord.from_kwargs(action='get', custom='v')
    r['post_extra'] = 1
    assert dict(_TRACE_BUCKETS) == {}


def test_trace_records_extras_at_construction(trace_on):
    """from_kwargs(extras=...) → __post_init__ records each key."""
    StatusRecord.from_kwargs(action='get', type='file',
                             annexkey='ABC123', metadata={'k': 1})
    keys = sorted(k for (k, _frame) in _TRACE_BUCKETS)
    assert keys == ['annexkey', 'metadata']
    # both record the producing action / type
    for (k, _frame), bucket in _TRACE_BUCKETS.items():
        assert bucket['count'] == 1
        assert bucket['actions'] == {'get': 1}
        assert bucket['types'] == {'file': 1}


def test_trace_records_extras_post_construction(trace_on):
    """r['unknown_key'] = v records via __setitem__ path."""
    r = StatusRecord(action='configure-sibling', type='sibling')
    r['name'] = 'origin'
    r['url'] = 'https://example.com'
    keys = sorted(k for (k, _frame) in _TRACE_BUCKETS)
    assert keys == ['name', 'url']
    for (k, _frame), bucket in _TRACE_BUCKETS.items():
        assert bucket['actions'] == {'configure-sibling': 1}
        assert bucket['types'] == {'sibling': 1}


def test_trace_does_not_record_declared_field_assignment(trace_on):
    """Declared-field writes don't go into telemetry — they're typed."""
    r = StatusRecord(action='get', path='/x', status='ok')
    r['status'] = 'notneeded'
    r.path = '/y'
    assert dict(_TRACE_BUCKETS) == {}


def test_trace_aggregates_repeated_writes(trace_on):
    """Same key from same frame → single bucket with count > 1."""
    for i in range(5):
        r = StatusRecord.from_kwargs(action='get', custom_key=i)
    # all five constructions go through the same call site
    buckets = list(_TRACE_BUCKETS.values())
    assert len(buckets) == 1
    assert buckets[0]['count'] == 5
    assert buckets[0]['value_types'] == {'int': 5}


def test_trace_value_type_diversity(trace_on):
    """Mixed value types in the same key, from the same call site, get
    aggregated; ``value_types`` records the diversity. Same call site
    means same source line — call from a helper to fix the line."""
    def _emit(v):
        return StatusRecord.from_kwargs(action='get', custom_key=v)
    _emit('string')
    _emit(42)
    buckets = list(_TRACE_BUCKETS.values())
    assert len(buckets) == 1                    # same (key, frame)
    assert buckets[0]['value_types'] == {'str': 1, 'int': 1}


def test_trace_distinct_frames_separate_buckets(trace_on):
    """Same key from different source lines → distinct buckets. This
    is the property that lets the v2.6 sweep aggregate per-call-site."""
    StatusRecord.from_kwargs(action='get', custom_key=1)  # call A
    StatusRecord.from_kwargs(action='get', custom_key=2)  # call B
    assert len(_TRACE_BUCKETS) == 2


def test_trace_examples_truncated_to_three(trace_on):
    """At most three example values per (key, frame) — bounded memory."""
    for i in range(10):
        StatusRecord.from_kwargs(action='get', sample=f'value-{i}')
    bucket = next(iter(_TRACE_BUCKETS.values()))
    assert len(bucket['examples']) == 3


def test_trace_dump_writes_jsonl(trace_on, tmp_path, monkeypatch):
    """_trace_dump() serialises buckets to JSONL at the configured path."""
    out = tmp_path / 'trace.jsonl'
    monkeypatch.setenv('DATALAD_STATUSRECORD_TRACE_PATH', str(out))
    StatusRecord.from_kwargs(action='get', custom='v')
    _trace_dump()
    assert out.exists()
    lines = out.read_text().splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec['key'] == 'custom'
    assert rec['count'] == 1
    assert rec['actions'] == {'get': 1}
    assert rec['value_types'] == {'str': 1}


def test_trace_dump_noop_when_disabled(trace_off, tmp_path, monkeypatch):
    """No file written when trace is off, even if buckets exist."""
    out = tmp_path / 'trace.jsonl'
    monkeypatch.setenv('DATALAD_STATUSRECORD_TRACE_PATH', str(out))
    _trace_dump()
    assert not out.exists()


def test_v23_v26_base_fields_are_typed():
    """v2.3 promoted four "in-the-wild" fields to base StatusRecord; v2.6
    moved the file-specific subset (``bytesize``, ``key``) onto
    ``FileStatusRecord`` based on the runtime telemetry sweep. The
    remaining cross-type fields (``gitshasum``, ``prev_gitshasum``)
    stay on the base.
    """
    on_base = ('gitshasum', 'prev_gitshasum')
    for name in on_base:
        assert name in StatusRecord._DECLARED_FIELDS_SET, \
            f'{name!r} should still be a declared base field (v2.3)'

    moved_to_file = ('bytesize', 'key')
    for name in moved_to_file:
        assert name not in StatusRecord._DECLARED_FIELDS_SET, \
            (f'{name!r} was moved off the base in v2.6 — runtime audit '
             f'confirmed it is file-specific. Should live on '
             f'FileStatusRecord.')

    r = StatusRecord(gitshasum='deadbeef', prev_gitshasum='cafebabe')
    assert r.gitshasum == 'deadbeef'
    assert r['gitshasum'] == 'deadbeef'
    assert r.prev_gitshasum == 'cafebabe'
    assert r._extras == {}


# ---------------------------------------------------------------------------
# v2.6: FileStatusRecord and SiblingStatusRecord
# ---------------------------------------------------------------------------

def test_file_status_record_declares_file_specific_fields():
    """v2.6: ``FileStatusRecord`` exposes the file-specific cluster as
    typed attributes."""
    from datalad.interface.results import FileStatusRecord

    expected = {
        # moved from base in v2.6
        'bytesize', 'key',
        # promoted from extras in v2.6 (each ≥2 frames in the sweep)
        'annexkey', 'backend', 'has_content', 'hashdirlower',
        'hashdirmixed', 'humansize', 'keyname', 'mtime', 'objloc',
    }
    for name in expected:
        assert name in FileStatusRecord._DECLARED_FIELDS_SET, \
            f'{name!r} should be a typed FileStatusRecord field'

    # base-class fields still accessible (subclass inherits)
    base = {'action', 'path', 'status', 'type', 'message',
            'gitshasum', 'prev_gitshasum'}
    for name in base:
        assert name in FileStatusRecord._DECLARED_FIELDS_SET, \
            f'{name!r} (base) should be inherited by FileStatusRecord'


def test_file_status_record_construction():
    from datalad.interface.results import FileStatusRecord

    r = FileStatusRecord(
        action='get', path='/x', status='ok', type='file',
        bytesize=1234, key='SHA256E-s1234--abc',
        annexkey='SHA256E-s1234--abc', has_content=True,
        humansize='1.2 KB',
    )
    assert r.bytesize == 1234
    assert r['bytesize'] == 1234
    assert r.key == 'SHA256E-s1234--abc'
    assert r['has_content'] is True
    # still a StatusRecord and a Mapping
    assert isinstance(r, StatusRecord)
    from collections.abc import Mapping as _Mapping
    assert isinstance(r, _Mapping)


def test_file_status_record_from_kwargs():
    """Permissive ``from_kwargs`` works on the subclass too: declared
    fields go to attributes, the rest to ``_extras``."""
    from datalad.interface.results import FileStatusRecord

    r = FileStatusRecord.from_kwargs(
        action='status', type='file', path='/x',
        bytesize=99, custom_extra='hi',
    )
    assert r.bytesize == 99
    assert r['custom_extra'] == 'hi'
    assert 'custom_extra' not in FileStatusRecord._DECLARED_FIELDS_SET


def test_sibling_status_record_declares_name():
    from datalad.interface.results import SiblingStatusRecord
    assert 'name' in SiblingStatusRecord._DECLARED_FIELDS_SET
    r = SiblingStatusRecord(
        action='configure-sibling', type='sibling', name='origin')
    assert r.name == 'origin'
    assert r['name'] == 'origin'
    # url stayed in extras per the v2.6 decision (single call site at
    # sweep time)
    r['url'] = 'https://example.com'
    assert r['url'] == 'https://example.com'
    assert 'url' not in SiblingStatusRecord._DECLARED_FIELDS_SET


def test_subclass_extras_keys_still_work():
    """Hyphenated keys (``annex-ignore``, ``gitmodule_*``-with-hyphens)
    must continue to flow through ``_extras`` on the subclasses, since
    they cannot be Python identifiers."""
    from datalad.interface.results import (
        FileStatusRecord,
        SiblingStatusRecord,
    )

    s = SiblingStatusRecord(name='origin')
    s['annex-ignore'] = 'false'
    s['annex-uuid'] = '00000000-...'
    assert s['annex-ignore'] == 'false'
    assert s['annex-uuid'] == '00000000-...'

    f = FileStatusRecord(type='file')
    f['some-weird-key'] = 1
    assert f['some-weird-key'] == 1


def test_subclass_isinstance_chain():
    """Existing consumers that test ``isinstance(r, StatusRecord)`` must
    still match subclass instances."""
    from datalad.interface.results import (
        FileStatusRecord,
        SiblingStatusRecord,
    )
    assert isinstance(FileStatusRecord(), StatusRecord)
    assert isinstance(SiblingStatusRecord(), StatusRecord)


def test_unset_sentinel_is_not_visible():
    r = StatusRecord()
    # _UNSET must never escape to a consumer
    for k in r:
        assert r[k] is not _UNSET
    for v in r.values():
        assert v is not _UNSET
    # writing _UNSET deletes the field
    r['action'] = 'get'
    r['action'] = _UNSET
    assert 'action' not in r
