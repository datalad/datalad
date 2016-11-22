# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test known annex meta data parser """

from os.path import join as opj
from datalad.distribution.dataset import Dataset
from datalad.api import create, install
from datalad.metadata.parsers.knownannexes import MetadataParser
from nose.tools import assert_true, assert_false, assert_equal
from datalad.tests.utils import with_tempfile


@with_tempfile(mkdir=True)
def test_has_metadata(path):
    ds = Dataset(path)
    p = MetadataParser(ds)
    assert_false(p.has_metadata())
    assert_equal(p.get_core_metadata_filenames(), [])
    ds.create()
    assert_true(p.has_metadata())


@with_tempfile(mkdir=True)
def test_get_metadata(path):
    create(opj(path, 'annexorigin'))
    clone = install(source=opj(path, 'annexorigin'), path=opj(path, 'annexclone'))
    meta = MetadataParser(clone).get_metadata('ID')
    # 2 annexes
    # 1 ds with annex info
    assert_equal(len(meta), 3)
    for m in meta:
        if m.get('@id') == 'ID':
            avail = m.get('availableFrom')
            # knows both annexes
            assert_equal(len(avail), 2)
        else:
            assert_equal(m.get('@type'), 'Annex')
            desc = m.get('Description')
            assert 'annexorigin' in desc or 'annexclone' in desc
