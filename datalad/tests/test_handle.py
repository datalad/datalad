# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test implementation of class Handle

"""

from nose import SkipTest
from nose.tools import assert_raises, assert_is_instance, assert_true, \
    assert_equal, assert_false, assert_is_not_none, assert_not_equal, assert_in, eq_, ok_

from ..support.handlerepo import HandleRepo, HandleRepoBackend
from ..support.handle import Handle, RuntimeHandle
from ..support.exceptions import ReadOnlyBackendError
from ..support.metadatahandler import URIRef, Literal, RDF, DLNS, Graph
from .utils import with_tempfile, with_testrepos, assert_cwd_unchanged, \
    ignore_nose_capturing_stdout, \
    on_windows, ok_clean_git, ok_clean_git_annex_proxy, \
    get_most_obscure_supported_name, swallow_outputs, ok_
from ..utils import get_local_file_url


def test_RuntimeHandle():

    name = "TestHandle"
    handle = RuntimeHandle(name)
    eq_(name, handle.name)
    ok_(handle.url is None)
    assert_is_instance(handle.meta, Graph)
    g = Graph(identifier="NewName")
    handle.meta = g
    eq_("NewName", handle.name)
    eq_(handle.meta, g)
    assert_raises(ReadOnlyBackendError, handle.commit_metadata)
    eq_("<Handle name=NewName "
        "(<class 'datalad.support.handle.RuntimeHandle'>)>",
        handle.__repr__())
