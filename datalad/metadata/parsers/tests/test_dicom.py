# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil; coding: utf-8 -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test audio parser"""

from datalad.tests.utils import SkipTest
try:
    import datalad.metadata.parsers.dicom
except ImportError:
    raise SkipTest

from shutil import copy
from os.path import dirname
from os.path import join as opj
from datalad.api import Dataset
from datalad.tests.utils import with_tempfile
from datalad.tests.utils import ok_clean_git
from datalad.tests.utils import assert_status
from datalad.tests.utils import assert_result_count
from datalad.tests.utils import eq_
from datalad.tests.utils import assert_dict_equal
from datalad.tests.utils import assert_in
from datalad.tests.utils import assert_not_in


@with_tempfile(mkdir=True)
def test_dicom(path):
    ds = Dataset(path).create()
    ds.config.add('datalad.metadata.nativetype', 'dicom', where='dataset')
    copy(
        opj(dirname(dirname(dirname(__file__))), 'tests', 'data', 'dicom.dcm'),
        path)
    ds.add('.')
    ok_clean_git(ds.path)
    res = ds.aggregate_metadata()
    assert_status('ok', res)
    # query for the file metadata
    res = ds.metadata('dicom.dcm')
    assert_result_count(res, 1)
    # from this parser
    meta = res[0]['metadata']['dicom']
    assert_in('@context', meta)
    # no point in testing ALL keys
    eq_(len(meta.keys()), 89)
    eq_(meta['SeriesDate'], '20070205')

    # now ask for the dataset metadata, which should have both the unique props
    # and a list of imageseries (one in this case, but a list)
    res = ds.metadata(reporton='datasets')
    assert_result_count(res, 1)
    dsmeta = res[0]['metadata']['dicom']
    # same context
    assert_dict_equal(meta['@context'], dsmeta['@context'])
    meta.pop('@context')
    eq_(dsmeta['Series'], [meta])

    # for this artificial case pretty much the same info also comes out as
    # unique props
    assert_dict_equal(
        dsmeta['Series'][0],
        res[0]['metadata']["datalad_unique_content_properties"]['dicom'])

    # buuuut, if we switch of file-based metadata storage
    ds.config.add('datalad.metadata.aggregate-content-dicom', 'false', where='dataset')
    ds.aggregate_metadata()
    res = ds.metadata(reporton='datasets')

    # the auto-uniquified bits are gone but the Series description stays
    assert_not_in("datalad_unique_content_properties", res[0]['metadata'])
    eq_(dsmeta['Series'], [meta])
