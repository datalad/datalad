# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil; coding: utf-8 -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test all parsers at a basic level"""

from inspect import isgenerator
from datalad.api import Dataset
from datalad.metadata import parsers
from nose.tools import assert_equal
from datalad.tests.utils import with_tree
from datalad.tests.utils import ok_clean_git


@with_tree(tree={'file.dat': ''})
def test_api(path):
    ds = Dataset(path).create(force=True)
    ds.add('.')
    ok_clean_git(ds.path)
    for p in dir(parsers):
        if p.startswith('_') or p in ('tests', 'base'):
            continue
        # we need to be able to query for metadata, even if there is none
        # from any parser
        meta = getattr(parsers, p).MetadataParser(
            ds, paths=['file.dat']).get_metadata(
                dataset=True,
                content=True)
        # we also get something for the dataset and something for the content
        # even if any of the two is empty
        assert_equal(len(meta), 2)
        dsmeta, contentmeta = meta
        assert (isinstance(dsmeta, dict))
        assert hasattr(contentmeta, '__len__') or isgenerator(contentmeta)
