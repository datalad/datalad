# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

import logging
import os.path as op

from datalad.support.json_py import (
    dump,
    dump2stream,
    dump2xzstream,
    load_stream,
    load_xzstream,
    load,
    loads,
    JSONDecodeError,
)

from datalad.tests.utils import (
    with_tempfile,
    eq_,
    assert_raises,
    assert_in,
    swallow_logs,
)


@with_tempfile(content=b'{"Authors": ["A1"\xc2\xa0, "A2"]}')
def test_load_screwy_unicode(fname):
    # test that we can tollerate some screwy unicode embeddings within json
    assert_raises(JSONDecodeError, load, fname, fixup=False)
    with swallow_logs(new_level=logging.WARNING) as cml:
        eq_(load(fname), {'Authors': ['A1', 'A2']})
        assert_in('Failed to decode content', cml.out)


def test_loads():
    eq_(loads('{"a": 2}'), {'a': 2})
    with assert_raises(JSONDecodeError),\
            swallow_logs(new_level=logging.WARNING) as cml:
        loads('{"a": 2}x')
    assert_in('Failed to load content from', cml.out)


@with_tempfile(mkdir=True)
def test_compression(path):
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
def test_dump(path):
    assert(not op.exists(path))
    # dump is nice and create the target directory
    dump('some', op.join(path, 'file.json'))
    assert(op.exists(path))


# at least a smoke test
@with_tempfile
def test_dump2stream(path):
    stream = [dict(a=5), dict(b=4)]
    dump2stream([dict(a=5), dict(b=4)], path)
    eq_(list(load_stream(path)), stream)

    # the same for compression
    dump2xzstream([dict(a=5), dict(b=4)], path)
    eq_(list(load_xzstream(path)), stream)
