# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test implementation of class Collection

"""

import os
from os.path import join as opj

from nose import SkipTest
from nose.tools import assert_raises, assert_equal, assert_false, assert_in
from rdflib import Graph, Literal
from rdflib.namespace import FOAF

from ..support.gitrepo import GitRepo
from ..support.handlerepo import HandleRepo
from ..support.collectionrepo import CollectionRepo, Collection
from ..tests.utils import with_tempfile, with_testrepos, assert_cwd_unchanged, \
    on_windows, ok_clean_git_annex_proxy, swallow_logs, swallow_outputs, in_, \
    with_tree, get_most_obscure_supported_name, ok_clean_git
from ..support.exceptions import CollectionBrokenError

# For now (at least) we would need to clone from the network
# since there are troubles with submodules on Windows.
# See: https://github.com/datalad/datalad/issues/44
local_flavors = ['network-clone' if on_windows else 'local']


@with_tempfile
def test_Collection_constructor(path):
    raise SkipTest
    # test _reload() separately?


def test_Collection_name():
    raise SkipTest


def test_Collection_setitem():
    raise SkipTest


def test_Collection_delitem():
    raise SkipTest


@with_tempfile
def test_Collection_commit(path):
    raise SkipTest