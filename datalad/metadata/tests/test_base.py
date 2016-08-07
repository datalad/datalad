# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test GNU-style meta data parser """

from datalad.api import Dataset
from datalad.metadata import get_metadata_type, get_metadata, get_dataset_identifier
from nose.tools import assert_true, assert_equal
from datalad.tests.utils import with_tree, with_tempfile
import os
from os.path import join as opj


@with_tempfile(mkdir=True)
def test_get_metadata_type(path):
    # nothing set, nothing found
    assert_equal(get_metadata_type(Dataset(path)), None)
    os.makedirs(opj(path, '.datalad'))
    # got section, but no setting
    open(opj(path, '.datalad', 'config'), 'w').write('[metadata]\n')
    assert_equal(get_metadata_type(Dataset(path)), None)
    # minimal setting
    open(opj(path, '.datalad', 'config'), 'w+').write('[metadata]\nnativetype = mamboschwambo\n')
    assert_equal(get_metadata_type(Dataset(path)), 'mamboschwambo')


@with_tempfile(mkdir=True)
def test_basic_metadata(path):
    ds = Dataset(opj(path, 'origin'))
    meta = get_metadata(ds)
    assert_equal(sorted(meta.keys()), ['@context', '@id'])
    ds.create()
    meta = get_metadata(ds)
    assert_equal(sorted(meta.keys()), ['@context', '@id', 'type'])
    assert_equal(meta['type'], 'Dataset')
    # clone and get relationship info in metadata
    sibling = Dataset(opj(path, 'sibling'))
    sibling.install(source=opj(path, 'origin'))
    sibling_meta = get_metadata(sibling)
    assert_equal(sibling_meta['dcterms:isVersionOf'],
                 {'@id': get_dataset_identifier(ds)})
    # origin should learn about the clone
    sibling.repo.push(remote='origin', refspec='git-annex')
    meta = get_metadata(ds)
    assert_equal(meta['dcterms:hasVersion'],
                 {'@id': get_dataset_identifier(sibling)})
