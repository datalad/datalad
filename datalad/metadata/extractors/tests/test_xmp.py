# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil; coding: utf-8 -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test XMP extractor"""

from datalad.tests.utils import (
    assert_in,
    assert_repo_status,
    assert_result_count,
    assert_status,
    eq_,
    SkipTest,
    with_tempfile,
)
try:
    import libxmp
except Exception as exc:
    from datalad.dochelpers import exc_str
    raise SkipTest("libxmp cannot be imported: %s" % exc_str(exc))

from shutil import copy
from os.path import (
    dirname,
    join as opj,
)
from datalad.api import Dataset


target = {
    'dc:creator': 'Michael Hanke',
    'dc:description': 'dlsubject',
    'dc:description<?xml:lang>': 'x-default',
    'dc:title': 'dltitle',
    'dc:title<?xml:lang>': 'x-default',
    'pdfaid:part': '1',
    'pdfaid:conformance': 'A',
    'pdf:Keywords': 'dlkeyword1 dlkeyword2',
    'pdf:Producer': 'LibreOffice 5.2',
    'xmp:CreateDate': '2017-10-08T10:27:06+02:00',
    'xmp:CreatorTool': 'Writer',
}


@with_tempfile(mkdir=True)
def test_xmp(path):
    ds = Dataset(path).create()
    ds.config.add('datalad.metadata.nativetype', 'xmp', where='dataset')
    copy(
        opj(dirname(dirname(dirname(__file__))), 'tests', 'data', 'xmp.pdf'),
        path)
    ds.save()
    assert_repo_status(ds.path)
    res = ds.aggregate_metadata()
    assert_status('ok', res)
    res = ds.metadata('xmp.pdf')
    assert_result_count(res, 1)

    # from this extractor
    meta = res[0]['metadata']['xmp']
    for k, v in target.items():
        eq_(meta[k], v)

    assert_in('@context', meta)
