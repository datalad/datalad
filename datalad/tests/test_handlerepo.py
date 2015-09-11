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
from os.path import join as opj, exists, basename, islink

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
@with_testrepos(flavors=local_testrepo_flavors)
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
@with_testrepos(flavors=local_testrepo_flavors)
@with_tempfile
def test_HandleRepo_direct(src, dst):

    ds = HandleRepo(dst, src, direct=True)
    assert_is_instance(ds, HandleRepo, "HandleRepo was not created.")
    assert_true(exists(opj(dst, '.datalad')))
    assert_true(ds.is_direct_mode(), "Forcing direct mode failed.")
    

@ignore_nose_capturing_stdout
@assert_cwd_unchanged
@with_testrepos(flavors=local_testrepo_flavors)
def test_Handle_instance_from_existing(path):

    raise SkipTest
    # TODO: provide a testrepo, which is a Handle already!
    # check for commit SHA, file content etc. Everything should
    # be identical

    gr = HandleRepo(path)
    assert_is_instance(gr, HandleRepo, "HandleRepo was not created.")
    assert_true(exists(opj(path, '.datalad')))


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


@ignore_nose_capturing_stdout
@with_testrepos(flavors=['network'])
@with_tempfile
def test_HandleRepo_get(src, dst):

    ds = HandleRepo(dst, src)
    assert_is_instance(ds, HandleRepo, "AnnexRepo was not created.")
    testfile = 'test-annex.dat'
    testfile_abs = opj(dst, testfile)
    assert_false(ds.file_has_content("test-annex.dat"))
    with swallow_outputs() as cmo:
        ds.get(testfile)
    assert_true(ds.file_has_content("test-annex.dat"))
    f = open(testfile_abs, 'r')
    assert_equal(f.readlines(), ['123\n'], "test-annex.dat's content doesn't match.")


@assert_cwd_unchanged
@with_testrepos(flavors=local_testrepo_flavors)
@with_tempfile
def test_HandleRepo_add_to_annex(src, dst):

    ds = HandleRepo(dst, src)
    filename = get_most_obscure_supported_name()
    filename_abs = opj(dst, filename)
    with open(filename_abs, 'w') as f:
        f.write("What to write?")
    ds.add_to_annex(filename)

    if not ds.is_direct_mode():
        assert_true(islink(filename_abs), "Annexed file is not a link.")
        ok_clean_git(dst, annex=True)
    else:
        assert_false(islink(filename_abs), "Annexed file is link in direct mode.")
        ok_clean_git_annex_proxy(dst)

    key = ds.get_file_key(filename)
    assert_false(key == '')
    # could test for the actual key, but if there's something and no exception raised, it's fine anyway.



@assert_cwd_unchanged
@with_testrepos(flavors=local_testrepo_flavors)
@with_tempfile
def test_HandleRepo_add_to_git(src, dst):

    ds = HandleRepo(dst, src)

    filename = get_most_obscure_supported_name()
    filename_abs = opj(dst, filename)
    with open(filename_abs, 'w') as f:
        f.write("What to write?")
    ds.add_to_git(filename_abs)

    if ds.is_direct_mode():
        ok_clean_git_annex_proxy(dst)
    else:
        ok_clean_git(dst, annex=True)
    assert_raises(FileInGitError, ds.get_file_key, filename)


@assert_cwd_unchanged
@with_testrepos(flavors=local_testrepo_flavors)
@with_tempfile
def test_HandleRepo_commit(src, path):

    ds = HandleRepo(path, src)
    filename = opj(path, get_most_obscure_supported_name())
    with open(filename, 'w') as f:
        f.write("File to add to git")
    ds.annex_add(filename)

    if ds.is_direct_mode():
        assert_raises(AssertionError, ok_clean_git_annex_proxy, path)
    else:
        assert_raises(AssertionError, ok_clean_git, path, annex=True)

    ds._commit("test _commit")
    if ds.is_direct_mode():
        ok_clean_git_annex_proxy(path)
    else:
        ok_clean_git(path, annex=True)


@with_tempfile
@with_tempfile
def test_HandleRepo_id(path1, path2):

    raise SkipTest

    # # check id is generated:
    # handle1 = HandleRepo(path1)
    # id1 = handle1.datalad_id()
    # assert_is_not_none(id1)
    # assert_is_instance(id1, basestring)
    # assert_equal(id1,
    #              handle1.repo.config_reader().get_value("annex", "uuid"))
    #
    # # check clone has same id:
    # handle2 = HandleRepo(path2, path1)
    # assert_equal(id1, handle2.datalad_id())


@with_tempfile
@with_tempfile
def test_HandleRepo_equals(path1, path2):

    handle1 = HandleRepo(path1)
    handle2 = HandleRepo(path1)
    ok_(handle1 == handle2)
    assert_equal(handle1, handle2)
    handle2 = HandleRepo(path2)
    assert_not_equal(handle1, handle2)
    ok_(handle1 != handle2)


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
