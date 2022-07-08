# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

from unittest.mock import patch

from datalad.support.annexrepo import AnnexRepo
from datalad.support.gitrepo import GitRepo
from datalad.support.repodates import check_dates
from datalad.tests.utils_pytest import (
    assert_equal,
    assert_false,
    assert_in,
    assert_not_in,
    assert_raises,
    eq_,
    ok_,
    set_date,
    with_tempfile,
    with_tree,
)


@with_tempfile(mkdir=True)
def test_check_dates_empty_repo(path=None):
    assert_false(check_dates(GitRepo(path, create=True))["objects"])


@with_tree(tree={"foo": "foo content",
                 "bar": "bar content"})
def test_check_dates(path=None):
    refdate = 1218182889

    with set_date(refdate - 1):
        ar = AnnexRepo(path, create=True)

        def tag_object(tag):
            """Return object for tag.  Do not dereference it.
            """
            # We can't use ar.get_tags because that returns the commit's hexsha,
            # not the tag's, and ar.get_hexsha is limited to commit objects.
            return ar.call_git_oneline(
                ["rev-parse", "refs/tags/{}".format(tag)], read_only=True)

        ar.add("foo")
        ar.commit("add foo")
        foo_commit = ar.get_hexsha()
        ar.commit("add foo")
        ar.tag("foo-tag", "tag before refdate")
        foo_tag = tag_object("foo-tag")
        # Make a lightweight tag to make sure `tag_dates` doesn't choke on it.
        ar.tag("light")
    with set_date(refdate + 1):
        ar.add("bar")
        ar.commit("add bar")
        bar_commit = ar.get_hexsha()
        ar.tag("bar-tag", "tag after refdate")
        bar_tag = tag_object("bar-tag")
    with set_date(refdate + 2):
        # Drop an annexed file so that we have more blobs in the git-annex
        # branch than its current tree.
        ar.drop("bar", options=["--force"])

    results = {}
    for which in ["older", "newer"]:
        result = check_dates(ar, refdate, which=which)["objects"]
        ok_(result)
        if which == "newer":
            assert_in(bar_commit, result)
            assert_not_in(foo_commit, result)
            assert_in(bar_tag, result)
        elif which == "older":
            assert_in(foo_commit, result)
            assert_not_in(bar_commit, result)
            assert_in(foo_tag, result)
        results[which] = result

    ok_(any(x.get("filename") == "uuid.log"
            for x in results["older"].values()))

    newer_tree = check_dates(ar, refdate, annex="tree")["objects"]

    def is_annex_log_blob(entry):
        return (entry["type"] == "annex-blob"
                and entry["filename"].endswith(".log"))

    def num_logs(entries):
        return sum(map(is_annex_log_blob, entries.values()))

    # Because we dropped bar above, we should have one more blob in the
    # git-annex branch than in the current tree of the git-annex branch.
    eq_(num_logs(results["newer"]) - num_logs(newer_tree), 1)

    # Act like today is one day from the reference timestamp to check that we
    # get the same results with the one-day-back default.
    seconds_in_day = 60 * 60 * 24
    with patch('time.time', return_value=refdate + seconds_in_day):
        assert_equal(check_dates(ar, annex="tree")["objects"],
                     newer_tree)

    # We can give a path (str) instead of a GitRepo object.
    assert_equal(check_dates(path, refdate, annex="tree")["objects"],
                 newer_tree)

    with assert_raises(ValueError):
        check_dates(ar, refdate, which="unrecognized")
