# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test file info meta data parser """

from simplejson import dumps
from datalad.distribution.dataset import Dataset
from datalad.api import create
from datalad.metadata.parsers.fileinfo import MetadataParser
from nose.tools import assert_true, assert_false, assert_equal, assert_not_in
from datalad.tests.utils import with_tree, with_tempfile
from datalad.support.gitrepo import GitRepo


@with_tempfile
def test_has_metadata(path):
    ds = Dataset(path)
    p = MetadataParser(ds)
    assert_false(p.has_metadata())
    GitRepo(path, create=True)
    assert_false(p.has_metadata())
    ds.create(force=True)
    assert_true(p.has_metadata())


@with_tree(tree={'test': {'subfile.tsv': "0\t1\t2\n"}})
def test_get_metadata(path):
    ds = Dataset(path).create(force=True)
    meta = MetadataParser(ds).get_metadata('ID')
    assert_equal(meta, [])
    ds.save(auto_add_changes=True)
    meta = MetadataParser(ds).get_metadata('ID')
    assert_equal(
        dumps(meta, sort_keys=True, indent=1),
        """\
[
 {
  "@context": "http://schema.datalad.org/",
  "@id": "MD5E-s6--1064e995efbe81d12fbdccf5e32954bf.tsv",
  "FileSize": 6,
  "Location": "test/subfile.tsv",
  "Type": "File",
  "conformsTo": "http://docs.datalad.org/metadata.html#v0-2"
 },
 {
  "@context": "http://schema.datalad.org/",
  "@id": "ID",
  "conformsTo": "http://docs.datalad.org/metadata.html#v0-2",
  "hasPart": [
   {
    "@id": "MD5E-s6--1064e995efbe81d12fbdccf5e32954bf.tsv"
   }
  ]
 }
]""")
    ds.config.add(
        'datalad.metadata.parser.fileinfo.report.filesize',
        'false',
        where='dataset')
    meta = MetadataParser(ds).get_metadata('ID')
    for m in meta:
        assert_not_in('FileSize', m)
