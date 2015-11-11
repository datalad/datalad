# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test implementation of class HandleRepo and HandleRepoBackend

"""

import os
from os.path import join as opj, exists, basename

from nose import SkipTest
from nose.tools import assert_raises, assert_is_instance, assert_true, \
    assert_equal, assert_false, assert_is_not_none, assert_not_equal, assert_in
from git.exc import GitCommandError
from rdflib import Graph, URIRef, Literal
from rdflib.namespace import RDF, FOAF

from ..support.handlerepo import HandleRepo, HandleRepoBackend, AnnexRepo
from ..support.exceptions import FileInGitError
from ..support.metadatahandler import DLNS, RDFS
from .utils import with_tempfile, with_testrepos, assert_cwd_unchanged, \
    ignore_nose_capturing_stdout, \
    on_windows, ok_clean_git, ok_clean_git_annex_proxy, \
    get_most_obscure_supported_name, swallow_outputs, ok_

from .utils import local_testrepo_flavors
from ..consts import REPO_CONFIG_FILE, REPO_STD_META_FILE

@ignore_nose_capturing_stdout
@assert_cwd_unchanged
@with_testrepos('.*handle.*', flavors=local_testrepo_flavors)
@with_tempfile
def test_HandleRepo(src, dst):

    ds = HandleRepo(dst, src)
    assert_is_instance(ds, HandleRepo, "HandleRepo was not created.")
    assert_true(exists(opj(dst, '.datalad')))

    # do it again should raise GitCommandError since git will notice there's
    # already a git-repo at that path
    assert_raises(GitCommandError, HandleRepo, dst, src)

    # TODO: test metadata and files

@ignore_nose_capturing_stdout
@assert_cwd_unchanged
@with_testrepos('.*handle.*', flavors=local_testrepo_flavors)
@with_tempfile
def test_HandleRepo_direct(src, dst):

    ds = HandleRepo(dst, src, direct=True)
    assert_is_instance(ds, HandleRepo, "HandleRepo was not created.")
    assert_true(exists(opj(dst, '.datalad')))
    assert_true(ds.is_direct_mode(), "Forcing direct mode failed.")
    

@ignore_nose_capturing_stdout
@assert_cwd_unchanged
@with_testrepos('.*handle.*', flavors=local_testrepo_flavors)
def test_Handle_instance_from_existing(path):

    # TODO: check for commit SHA, file content etc. Everything should
    # be identical

    gr = HandleRepo(path, create=False, init=False)
    assert_is_instance(gr, HandleRepo, "HandleRepo was not created.")


@ignore_nose_capturing_stdout
@assert_cwd_unchanged
@with_tempfile
def test_HandleRepo_instance_brand_new(path):

    annex = AnnexRepo(path)
    h1 = HandleRepo(path, create=False)
    assert_is_instance(h1, HandleRepo, "HandleRepo was not created.")
    assert_false(exists(opj(path, '.datalad')))
    assert_false(exists(opj(path, '.datalad', REPO_STD_META_FILE)))
    assert_false(exists(opj(path, '.datalad', REPO_CONFIG_FILE)))

    h2 = HandleRepo(path)
    assert_is_instance(h2, HandleRepo, "HandleRepo was not created.")
    assert_true(exists(opj(path, '.datalad')))
    assert_true(exists(opj(path, '.datalad', REPO_STD_META_FILE)))
    assert_true(exists(opj(path, '.datalad', REPO_CONFIG_FILE)))


@with_tempfile
def test_HandleRepo_name(path):
    # tests get_name and set_name
    h = HandleRepo(path)
    assert_equal(h.name, basename(path))
    h.name = "new_name"
    assert_equal(Graph().parse(opj(path, '.datalad', REPO_CONFIG_FILE),
                               format="turtle").value(subject=DLNS.this,
                                                      predicate=RDFS.label),
                 Literal("new_name"))
    assert_equal(h.name, "new_name")


@with_tempfile
def test_HandleRepo_get_metadata(path):
    repo = HandleRepo(path)

    # default
    graph = repo.get_metadata()
    assert_in((DLNS.this, RDF.type, DLNS.Handle),
              graph)
    assert_in((DLNS.this, RDFS.label, Literal(repo.name)),
              graph)
    assert_equal(len(graph), 2)
    assert_equal(graph.identifier, URIRef(repo.name))

    # single file:
    graph2 = repo.get_metadata([REPO_STD_META_FILE])
    assert_in((DLNS.this, RDF.type, DLNS.Handle),
              graph2)
    assert_equal(len(graph2), 1)




# testing HandleRepoBackend:

@with_tempfile
def test_HandleRepoBackend_constructor(path):
    repo = HandleRepo(path)
    backend = HandleRepoBackend(repo)
    assert_equal(backend._branch, repo.git_get_active_branch())
    assert_equal(backend._repo, repo)
    assert_equal(backend.url, repo.path)


@with_tempfile
def test_HandleRepoBackend_name(path):
    repo = HandleRepo(path)
    backend = HandleRepoBackend(repo)

    # get name:
    assert_equal(backend.name, repo.name)

    # set name:
    backend.name = "new_name"
    assert_equal(backend.name, "new_name")
    assert_equal(repo.name, "new_name")


@with_tempfile
def test_HandleRepoBackend_metadata(path):
    repo = HandleRepo(path)
    backend = HandleRepoBackend(repo)
    assert_equal(backend.metadata,
                 repo.get_metadata())
    assert_equal(backend.metadata.identifier,
                 URIRef(repo.name))
