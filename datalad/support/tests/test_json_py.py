# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-; coding: utf-8 -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

import logging
import os.path as op

from datalad.support.json_py import (
    JSONDecodeError,
    dump,
    dump2stream,
    dump2xzstream,
    load,
    load_stream,
    load_xzstream,
    loads,
)
from datalad.tests.utils_pytest import (
    assert_in,
    assert_raises,
    eq_,
    swallow_logs,
    with_tempfile,
)


@with_tempfile(content=b'{"Authors": ["A1"\xc2\xa0, "A2"]}')
def test_load_screwy_unicode(fname=None):
    # test that we can tollerate some screwy unicode embeddings within json
    assert_raises(JSONDecodeError, load, fname, fixup=False)
    with swallow_logs(new_level=logging.WARNING) as cml:
        eq_(load(fname), {'Authors': ['A1', 'A2']})
        assert_in('Failed to decode content', cml.out)


@with_tempfile(content=u"""\
{"key0": "a b"}
{"key1": "plain"}""".encode("utf-8"))
def test_load_unicode_line_separator(fname=None):
    # See gh-3523.
    result = list(load_stream(fname))
    eq_(len(result), 2)
    eq_(result[0]["key0"], u"a b")
    eq_(result[1]["key1"], u"plain")


def test_loads():
    eq_(loads('{"a": 2}'), {'a': 2})
    with assert_raises(JSONDecodeError),\
            swallow_logs(new_level=logging.WARNING) as cml:
        loads('{"a": 2}x')
    assert_in('Failed to load content from', cml.out)


@with_tempfile(mkdir=True)
def test_compression(path=None):
    fname = op.join(path, 'test.json.xz')
    content = 'dummy'
    # dump compressed
    dump(content, fname, compressed=True)
    # filename extension match auto-enabled compression "detection"
    eq_(load(fname), content)
    # but was it actually compressed?
    # we don't care how exactly it blows up (UnicodeDecodeError, etc),
    # but it has to blow
    assert_raises(Exception, load, fname, compressed=False)


@with_tempfile
def test_dump(path=None):
    assert(not op.exists(path))
    # dump is nice and create the target directory
    dump('some', op.join(path, 'file.json'))
    assert(op.exists(path))


# at least a smoke test
@with_tempfile
def test_dump2stream(path=None):
    stream = [dict(a=5), dict(b=4)]
    dump2stream([dict(a=5), dict(b=4)], path)
    eq_(list(load_stream(path)), stream)

    # the same for compression
    dump2xzstream([dict(a=5), dict(b=4)], path)
    eq_(list(load_xzstream(path)), stream)
