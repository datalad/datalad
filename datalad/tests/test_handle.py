# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test implementation of classes Handle, RuntimeHandle

"""

from nose.tools import assert_is_instance

from ..support.handle import Handle, RuntimeHandle
from ..support.exceptions import ReadOnlyBackendError
from ..support.metadatahandler import RDF, DLNS, Graph
from .utils import ok_, eq_, assert_raises


def test_RuntimeHandle():

    name = "TestHandle"
    handle = RuntimeHandle(name)
    assert_is_instance(handle, Handle)
    eq_(name, handle.name)
    ok_(handle.url is None)
    assert_is_instance(handle.meta, Graph)
    eq_(handle.meta.value(subject=DLNS.this, predicate=RDF.type), DLNS.Handle)
    g = Graph(identifier="NewName")
    handle.meta = g
    eq_("NewName", handle.name)
    eq_(handle.meta, g)
    assert_raises(ReadOnlyBackendError, handle.commit_metadata)
    eq_("<Handle name=NewName "
        "(<class 'datalad.support.handle.RuntimeHandle'>)>",
        handle.__repr__())

