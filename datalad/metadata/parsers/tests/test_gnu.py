# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test GNU-style meta data parser """

from datalad.distribution.dataset import Dataset
from datalad.metadata.parsers.gnu import has_metadata, get_metadata
from nose.tools import assert_true
from datalad.tests.utils import with_tree


@with_tree(tree={
    'README': 'some description',
    'COPYING': 'some license',
    'AUTHOR': 'some authors'})
def test_has_metadata(path):
    assert_true(has_metadata(Dataset(path)))
