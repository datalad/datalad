# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Tests for filter expression parsing and matching"""

from pathlib import PurePosixPath

import pytest

from datalad.support.filter import (
    _resolve_filter_key,
    match_filter,
    match_filters,
    parse_filter_spec,
)
from datalad.utils import Path

# -- parse_filter_spec --------------------------------------------------------

@pytest.mark.ai_generated
@pytest.mark.parametrize("expr,expected", [
    ('url=http://example.com', ('url', '=', 'http://example.com')),
    ('url!=http://example.com', ('url', '!=', 'http://example.com')),
    ('url~=^\\.\\.\\//', ('url', '~=', '^\\.\\.\\//')),
    ('url!~^\\.\\.\\//', ('url', '!~', '^\\.\\.\\//')),
    ('datalad-id?', ('datalad-id', '?', '')),
    ('datalad-id!?', ('datalad-id', '!?', '')),
    ('.state=present', ('.state', '=', 'present')),
    ('.state?', ('.state', '?', '')),
    ('url=', ('url', '=', '')),
    # value can contain = signs
    ('url=http://x.com?a=1', ('url', '=', 'http://x.com?a=1')),
])
def test_parse_filter_spec(expr, expected):
    assert parse_filter_spec(expr) == expected


@pytest.mark.ai_generated
@pytest.mark.parametrize("expr", [
    '',
    None,
    'justakeyword',
    '123=value',
    'key@name=value',
])
def test_parse_filter_spec_invalid(expr):
    with pytest.raises(ValueError):
        parse_filter_spec(expr)


# -- _resolve_filter_key ------------------------------------------------------

@pytest.mark.ai_generated
@pytest.mark.parametrize("key,record,expected", [
    # bare key found
    ('url', {'gitmodule_url': 'http://example.com'}, ('http://example.com', True)),
    # bare key not found
    ('url', {'state': 'present'}, ('', False)),
    # dot key found
    ('.state', {'state': 'present'}, ('present', True)),
    # dot key not found
    ('.state', {'gitmodule_url': 'http://example.com'}, ('', False)),
    # Path converted to str
    ('.path', {'path': PurePosixPath('/some/path')}, ('/some/path', True)),
    # bare key with hyphen
    ('datalad-id', {'gitmodule_datalad-id': 'abc123'}, ('abc123', True)),
])
def test_resolve_filter_key(key, record, expected):
    assert _resolve_filter_key(key, record) == expected


# -- match_filter -------------------------------------------------------------

# Shared record for match_filter tests
_RECORD = {
    'gitmodule_url': 'http://example.com/repo',
    'gitmodule_name': 'sub1',
    'gitmodule_datalad-id': 'abc-123',
    'state': 'present',
    'path': Path('/ds/sub1'),
}


@pytest.mark.ai_generated
@pytest.mark.parametrize("parsed_filter,expected", [
    # = operator
    (('url', '=', 'http://example.com/repo'), True),
    (('url', '=', 'http://other.com'), False),
    # != operator
    (('url', '!=', 'http://other.com'), True),
    (('url', '!=', 'http://example.com/repo'), False),
    # ~= operator (re.search, not re.match)
    (('url', '~=', r'example\.com'), True),
    (('url', '~=', r'^other'), False),
    (('url', '~=', 'repo'), True),  # search finds pattern anywhere
    # !~ operator
    (('url', '!~', r'^other'), True),
    (('url', '!~', r'example\.com'), False),
    # ? operator
    (('url', '?', ''), True),
    (('nonexistent', '?', ''), False),
    # !? operator
    (('nonexistent', '!?', ''), True),
    (('url', '!?', ''), False),
    # dot-prefixed key
    (('.state', '=', 'present'), True),
    (('.state', '=', 'absent'), False),
    # missing key with comparison operators — always no match
    (('nonexistent', '=', 'value'), False),
    (('nonexistent', '!=', 'value'), False),
    (('nonexistent', '~=', '.*'), False),
    (('nonexistent', '!~', '.*'), False),
])
def test_match_filter(parsed_filter, expected):
    assert match_filter(_RECORD, parsed_filter) == expected


# -- match_filters ------------------------------------------------------------

_RECORD_RELATIVE = {
    'gitmodule_url': '../../sourcedata/raw',
    'gitmodule_name': 'sub1',
    'state': 'absent',
    'path': Path('/ds/sub1'),
}


@pytest.mark.ai_generated
@pytest.mark.parametrize("filters,expected", [
    # empty → matches everything
    ([], True),
    # single filter
    ([('.state', '=', 'absent')], True),
    ([('.state', '=', 'present')], False),
    # AND: all match
    ([('.state', '=', 'absent'), ('url', '~=', r'^\.\.'),], True),
    # AND: one fails
    ([('.state', '=', 'present'), ('url', '~=', r'^\.\.'),], False),
    # AND: all fail
    ([('.state', '=', 'present'), ('url', '=', 'http://example.com'),], False),
    # missing property
    ([('custom-tag', '=', 'core')], False),
    ([('custom-tag', '?', '')], False),
    ([('custom-tag', '!?', '')], True),
])
def test_match_filters(filters, expected):
    assert match_filters(_RECORD_RELATIVE, filters) == expected
