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
    _UNSET,
    StatusRecord,
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


def test_in_the_wild_fields_are_typed_attributes():
    """v2.3 promotion: fields explicitly listed in
    ``docs/source/design/result_records.rst`` as commonly-observed across
    commands are exposed as typed attributes rather than living in
    ``_extras``. Pin the specific set so a future regression cannot
    silently demote them.
    """
    promoted = ('bytesize', 'gitshasum', 'prev_gitshasum', 'key')
    for name in promoted:
        assert name in StatusRecord._DECLARED_FIELDS_SET, \
            f'{name!r} should be a declared StatusRecord field (v2.3)'

    r = StatusRecord(
        bytesize=1234,
        gitshasum='deadbeef',
        prev_gitshasum='cafebabe',
        key='SHA256E-s12345--abc',
    )
    # accessible via both attribute and item style
    assert r.bytesize == 1234
    assert r['bytesize'] == 1234
    assert r.gitshasum == 'deadbeef'
    assert r['gitshasum'] == 'deadbeef'
    assert r.prev_gitshasum == 'cafebabe'
    assert r.key == 'SHA256E-s12345--abc'
    # not in _extras
    assert r._extras == {}


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
