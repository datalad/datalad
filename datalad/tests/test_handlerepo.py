# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test implementation of class HandleRepo

"""

from git.exc import GitCommandError
from os.path import join as opj, exists, basename

from nose.tools import assert_raises, assert_is_instance, assert_true, \
    assert_equal, assert_false, assert_in
from rdflib import Graph, URIRef, Literal
from rdflib.namespace import RDF

from .utils import local_testrepo_flavors
from .utils import with_tempfile, with_testrepos, assert_cwd_unchanged, \
    ignore_nose_capturing_stdout, \
    ok_clean_git, ok_, ok_startswith, eq_
from ..consts import REPO_CONFIG_FILE, REPO_STD_META_FILE, HANDLE_META_DIR
from ..support.handlerepo import HandleRepo, AnnexRepo
from ..support.metadatahandler import DLNS, RDFS


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
    repo = HandleRepo(path, create=True)

    # default
    graphs = repo.get_metadata()
    eq_(len(graphs), 2)  # just datalad.ttl and config.ttl
    assert_in(REPO_CONFIG_FILE[:-4], graphs)
    assert_in(REPO_STD_META_FILE[:-4], graphs)
    assert_in((DLNS.this, RDF.type, DLNS.Handle),
              graphs[REPO_STD_META_FILE[:-4]])
    assert_in((DLNS.this, RDFS.label, Literal(repo.name)),
              graphs[REPO_CONFIG_FILE[:-4]])

    # TODO: Use handle with several metadata files and
    # only load them partially.


@with_tempfile
def test_HandleRepo_set_metadata(path):
    repo = HandleRepo(path, create=True)

    metadata = dict()
    metadata['graph1'] = Graph()
    metadata['graph1'].add((URIRef("http://example.org"),
                            RDF.type,
                            DLNS.FakeTerm))

    repo.set_metadata(metadata)
    ok_clean_git(path, annex=True)
    target_file_1 = opj(path, HANDLE_META_DIR, "graph1.ttl")
    ok_(exists(target_file_1))
    eq_(set(iter(metadata['graph1'])),
        set(iter(Graph().parse(target_file_1, format="turtle"))))

    # not existing branch:
    with assert_raises(ValueError) as cm:
        repo.set_metadata(metadata, branch="notexisting")
    ok_startswith(str(cm.exception), "Unknown branch")

    # create new branch and switch back:
    repo.git_checkout("new_branch", "-b")
    repo.git_checkout("master")

    # store metadata to not checked-out branch:
    metadata['graph2'] = Graph()
    metadata['graph2'].add((URIRef("http://example.org"),
                            RDF.type,
                            DLNS.AnotherFakeTerm))
    target_file_2 = opj(path, HANDLE_META_DIR, "graph2.ttl")
    repo.set_metadata(metadata, branch="new_branch")

    ok_clean_git(path, annex=True)
    eq_(repo.git_get_active_branch(), "master")
    ok_(not exists(target_file_2))

    repo.git_checkout("new_branch")
    ok_(exists(target_file_1))
    ok_(exists(target_file_2))
    eq_(set(iter(metadata['graph1'])),
        set(iter(Graph().parse(target_file_1, format="turtle"))))
    eq_(set(iter(metadata['graph2'])),
        set(iter(Graph().parse(target_file_2, format="turtle"))))

    # element of wrong type:
    metadata['second'] = list()
    with assert_raises(TypeError) as cm:
        repo.set_metadata(metadata)
    ok_startswith(str(cm.exception),
                  "Wrong type of graphs['second'] (%s)" % list)

    # parameter of wrong type:
    with assert_raises(TypeError) as cm:
        repo.set_metadata([1, 2])
    ok_startswith(str(cm.exception),
                  "Unexpected type of parameter 'graphs' (%s)" % list)
