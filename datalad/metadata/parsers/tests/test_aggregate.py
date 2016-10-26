# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test aggregate meta data parser """

import os
from os.path import join as opj
from datalad.distribution.dataset import Dataset
from datalad.api import create
from datalad.metadata.parsers.aggregate import MetadataParser
from nose.tools import assert_true, assert_false, assert_equal
from datalad.tests.utils import with_tempfile


@with_tempfile(mkdir=True)
def test_basic(path):
    ds = Dataset(path).create()
    p = MetadataParser(ds)
    assert_false(p.has_metadata())
    mpath = opj(ds.path, '.datalad', 'meta', 'something', 'deep')
    os.makedirs(mpath)
    assert_false(p.has_metadata())
    with open(opj(mpath, 'meta.json'), 'w') as fp:
        fp.write('{"name": "testmonkey", "dcterms:isPartOf": "%s", "@id": "unique"}' % ds.id)
    assert_true(p.has_metadata())
    #from datalad.metadata import get_metadata
    #from json import dumps
    #print(dumps(get_metadata(ds), indent=1))
    #assert_equal(
    #    p.get_metadata(),
    #    [{'dcterms:hasPart': {'location': 'something/deep'}}])
