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
    assert_equal, assert_false, assert_is_not_none, assert_not_equal, assert_in

from ..support.handlerepo import HandleRepo, HandleRepoBackend
from ..support.handle import Handle
from ..support.metadatahandler import URIRef, Literal, RDF, DLNS
from .utils import with_tempfile, with_testrepos, assert_cwd_unchanged, \
    ignore_nose_capturing_stdout, \
    on_windows, ok_clean_git, ok_clean_git_annex_proxy, \
    get_most_obscure_supported_name, swallow_outputs, ok_
from ..utils import get_local_file_url


@with_tempfile
def test_Handle_constructor(path):
    repo = HandleRepo(path)
    # backend constructor
    handle = Handle(HandleRepoBackend(repo))
    assert_equal(handle.url, repo.path)
    assert_in((DLNS.this, RDF.type, DLNS.Handle),
              handle.meta)

    # copy constructor:
    handle2 = Handle(handle)
    assert_equal(handle2.url, repo.path)
    assert_in((DLNS.this, RDF.type, DLNS.Handle),
              handle2.meta)

    # empty:
    handle3 = Handle(name="empty_handle")
    assert_equal(handle3.meta.identifier, Literal("empty_handle"))
    assert_in((DLNS.this, RDF.type, DLNS.Handle),
              handle.meta)


@with_tempfile
def test_Handle_meta(path):
    repo = HandleRepo(path)
    repo_md = repo.get_metadata()
    handle = Handle(HandleRepoBackend(repo))
    assert_equal(handle.name, URIRef(repo.name))
    assert_equal(handle.name, handle.meta.identifier)
    [assert_in(triple, handle.meta) for triple in repo_md]
    assert_equal(len(handle.meta), len(repo_md))
    assert_equal(handle.meta.identifier, repo_md.identifier)

    # TODO: set metadata. (See handlerepo)
    #       set name?


def test_Handle_commit():
    raise SkipTest
