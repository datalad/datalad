# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test frictionless datapackage meta data parser """

from os.path import join as opj
from simplejson import dumps
from datalad.distribution.dataset import Dataset
from datalad.metadata.parsers.frictionless_datapackage import MetadataParser
from nose.tools import assert_true, assert_false, assert_equal
from datalad.tests.utils import with_tree, with_tempfile


@with_tree(tree={'datapackage.json': '{"name": "some"}'})
def test_has_metadata(path):
    ds = Dataset(path)
    p = MetadataParser(ds)
    assert_true(p.has_metadata())
    assert_equal(p.get_metadata_filenames(),
                 [opj(path, 'datapackage.json')])


@with_tempfile(mkdir=True)
def test_has_no_metadata(path):
    ds = Dataset(path)
    p = MetadataParser(ds)
    assert_false(p.has_metadata())
    assert_equal(p.get_core_metadata_filenames(), [])


# bits from examples and the specs
@with_tree(tree={'datapackage.json': """
{
  "name": "cpi",
  "title": "Annual Consumer Price Index (CPI)",
  "description": "Annual Consumer Price Index (CPI) for most countries in the world. Reference year is 2005.",
  "license" : {
      "type": "odc-pddl",
      "url": "http://opendatacommons.org/licenses/pddl/"
  },
  "keywords": [ "CPI", "World", "Consumer Price Index", "Annual Data", "The World Bank" ],
  "version": "2.0.0",
  "last_updated": "2014-09-22",
  "contributors": [
    {
      "name": "Joe Bloggs",
      "email": "joe@example.com",
      "web": "http://www.example.com"
    }
  ],
  "author": "Jane Doe <noemail@example.com>"
}
"""})
def test_get_metadata(path):

    ds = Dataset(path)
    p = MetadataParser(ds)
    meta = p.get_metadata('ID')
    assert_equal(
        dumps(meta, sort_keys=True, indent=2),
        """\
{
  "@context": {
    "@vocab": "http://schema.org/",
    "doap": "http://usefulinc.com/ns/doap#"
  },
  "@id": "ID",
  "author": "Jane Doe <noemail@example.com>",
  "contributors": [
    "Joe Bloggs <joe@example.com> (http://www.example.com)"
  ],
  "dcterms:conformsTo": [
    "http://specs.frictionlessdata.io/data-packages",
    "http://docs.datalad.org/metadata.html#v0-1"
  ],
  "description": "Annual Consumer Price Index (CPI) for most countries in the world. Reference year is 2005.",
  "keywords": [
    "CPI",
    "World",
    "Consumer Price Index",
    "Annual Data",
    "The World Bank"
  ],
  "license": "http://opendatacommons.org/licenses/pddl/",
  "name": "cpi",
  "title": "Annual Consumer Price Index (CPI)",
  "version": "2.0.0"
}""")
