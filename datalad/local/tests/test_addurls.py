# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# -*- coding: utf-8 -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test addurls"""

import json
import logging
import os
import os.path as op
import shutil
import tempfile
from copy import deepcopy
from io import StringIO
from unittest.mock import patch
from urllib.parse import urlparse

import pytest

import datalad.local.addurls as au
from datalad import cfg as dl_cfg
from datalad.api import (
    Dataset,
    addurls,
    subdatasets,
)
from datalad.cmd import WitlessRunner
from datalad.consts import WEB_SPECIAL_REMOTE_UUID
from datalad.support.exceptions import IncompleteResultsError
from datalad.support.external_versions import external_versions
from datalad.tests.utils_pytest import (
    DEFAULT_BRANCH,
    HTTPPath,
    SkipTest,
    assert_dict_equal,
    assert_false,
    assert_in,
    assert_in_results,
    assert_not_in,
    assert_raises,
    assert_re_in,
    assert_repo_status,
    assert_result_count,
    assert_true,
    chpwd,
    create_tree,
    eq_,
    known_failure_githubci_win,
    ok_exists,
    ok_file_has_content,
    ok_startswith,
    on_windows,
    skip_if,
    swallow_logs,
    swallow_outputs,
    with_tempfile,
    with_tree,
)
from datalad.utils import (
    get_tempfile_kwargs,
    rmtemp,
)


def test_formatter():
    idx_to_name = {i: "col{}".format(i) for i in range(4)}
    values = {"col{}".format(i): "value{}".format(i) for i in range(4)}

    fmt = au.Formatter(idx_to_name)

    eq_(fmt.format("{0}", values), "value0")
    eq_(fmt.format("{0}", values), fmt.format("{col0}", values))

    # Integer placeholders outside of `idx_to_name` don't work.
    assert_raises(KeyError, fmt.format, "{4}", values, 1, 2, 3, 4)

    # If the named placeholder is not in `values`, falls back to normal
    # formatting.
    eq_(fmt.format("{notinvals}", values, notinvals="ok"), "ok")


def test_formatter_lower_case():
    fmt = au.Formatter({0: "key"})
    eq_(fmt.format("{key!l}", {"key": "UP"}), "up")
    eq_(fmt.format("{0!l}", {"key": "UP"}), "up")
    eq_(fmt.format("{other!s}", {}, other=[1, 2]), "[1, 2]")


def test_formatter_no_idx_map():
    fmt = au.Formatter({})
    assert_raises(KeyError, fmt.format, "{0}", {"col0": "value0"})


def test_formatter_no_mapping_arg():
    fmt = au.Formatter({})
    with assert_raises(ValueError) as cme:
        fmt.format("{0}", "not a mapping")
    # we provide that detail/element in a message
    assert_in("not a mapping", str(cme.value))


def test_formatter_placeholder_with_spaces():
    fmt = au.Formatter({})
    eq_(fmt.format("{with spaces}", {"with spaces": "value0"}), "value0")


def test_formatter_placeholder_nonpermitted_chars():
    fmt = au.Formatter({})

    # Can't assess keys with !, which will be interpreted as a conversion flag.
    eq_(fmt.format("{key!r}", {"key!r": "value0"}, key="x"), "'x'")
    assert_raises(KeyError,
                  fmt.format, "{key!r}", {"key!r": "value0"})

    # Same for ":".
    eq_(fmt.format("{key:<5}", {"key:<5": "value0"}, key="x"), "x    ")
    assert_raises(KeyError,
                  fmt.format, "{key:<5}", {"key:<5": "value0"})


def test_formatter_missing_arg():
    fmt = au.Formatter({}, "NA")
    eq_(fmt.format("{here},{nothere}", {"here": "ok", "nothere": ""}),
        "ok,NA")


def test_repformatter():
    fmt = au.RepFormatter({})

    for i in range(3):
        eq_(fmt.format("{c}{_repindex}", {"c": "x"}), "x{}".format(i))
    # A new result gets a fresh index.
    for i in range(2):
        eq_(fmt.format("{c}{_repindex}", {"c": "y"}), "y{}".format(i))
    # We count even if _repindex isn't there.
    eq_(fmt.format("{c}", {"c": "z0"}), "z0")
    eq_(fmt.format("{c}{_repindex}", {"c": "z"}), "z1")


def test_clean_meta_args():
    for args, expect in [(["field="], {}),
                         ([" field=yes "], {"field": "yes"}),
                         (["field= value="], {"field": "value="})]:
        eq_(au.clean_meta_args(args), expect)

    assert_raises(ValueError,
                  au.clean_meta_args,
                  ["noequal"])
    assert_raises(ValueError,
                  au.clean_meta_args,
                  ["=value"])


def test_get_subpaths():
    for fname, expect in [
            (op.join("no", "dbl", "slash"),
             (op.join("no", "dbl", "slash"), [])),
            ("p1//n",
             (op.join("p1", "n"), ["p1"])),
            (op.join("p1//p2", "p3//n"),
             (op.join("p1", "p2", "p3", "n"),
              ["p1", op.join("p1", "p2", "p3")])),
            (op.join("p1//p2", "p3//p4", "p5//", "n"),
             (op.join("p1", "p2", "p3", "p4", "p5", "n"),
              ["p1",
               op.join("p1", "p2", "p3"),
               op.join("p1", "p2", "p3", "p4", "p5")])),
            ("//n", (op.sep + "n", [""])),
            ("n//", ("n" + op.sep, ["n"]))]:
        eq_(au.get_subpaths(fname), expect)


def test_sort_paths():
    paths = [op.join("x", "a", "b"),
             "z",
             op.join("y", "b"),
             op.join("y", "a")]
    expected = ["z",
                op.join("y", "a"),
                op.join("y", "b"),
                op.join("x", "a", "b")]
    eq_(list(au.sort_paths(paths)), expected)


def test_is_legal_metafield():
    for legal in ["legal", "0", "legal_"]:
        assert_true(au.is_legal_metafield(legal))
    for notlegal in ["_not", "with space"]:
        assert_false(au.is_legal_metafield(notlegal))


def test_filter_legal_metafield():
    eq_(au.filter_legal_metafield(["legal", "_not", "legal_still"]),
        ["legal", "legal_still"])


def test_fmt_to_name():
    eq_(au.fmt_to_name("{name}", {}), "name")
    eq_(au.fmt_to_name("{0}", {0: "name"}), "name")
    eq_(au.fmt_to_name("{1}", {0: "name"}), "1")

    assert_false(au.fmt_to_name("frontmatter{name}", {}))
    assert_false(au.fmt_to_name("{name}backmatter", {}))
    assert_false(au.fmt_to_name("{two}{names}", {}))
    assert_false(au.fmt_to_name("", {}))
    assert_false(au.fmt_to_name("nonames", {}))
    assert_false(au.fmt_to_name("{}", {}))


def test_get_file_parts():
    assert_dict_equal(au.get_file_parts("file.tar.gz", "prefix"),
                      {"prefix": "file.tar.gz",
                       "prefix_root_py": "file.tar",
                       "prefix_ext_py": ".gz",
                       "prefix_root": "file",
                       "prefix_ext": ".tar.gz"})


def test_get_url_parts():
    eq_(au.get_url_parts(""), {})
    assert_dict_equal(au.get_url_parts("http://datalad.org"),
                      {"_url_hostname": "datalad.org"})

    assert_dict_equal(au.get_url_parts("http://datalad.org/about.html"),
                      {"_url_hostname": "datalad.org",
                       "_url0": "about.html",
                       "_url_basename": "about.html",
                       "_url_basename_root_py": "about",
                       "_url_basename_ext_py": ".html",
                       "_url_basename_root": "about",
                       "_url_basename_ext": ".html"})
    assert_dict_equal(au.get_url_parts("http://datalad.org/about.html"),
                      au.get_url_parts("http://datalad.org//about.html"))

    assert_dict_equal(
        au.get_url_parts("http://datalad.org/for/git-users"),
        {"_url_hostname": "datalad.org",
         "_url0": "for",
         "_url1": "git-users",
         "_url_basename": "git-users",
         "_url_basename_root_py": "git-users",
         "_url_basename_ext_py": "",
         "_url_basename_root": "git-users",
         "_url_basename_ext": ""})


ST_DATA = {"header": ["name", "debut_season", "age_group", "now_dead"],
           "rows": [{"name": "will", "debut_season": 1,
                     "age_group": "kid", "now_dead": "no"},
                    {"name": "bob", "debut_season": 2,
                     "age_group": "adult", "now_dead": "yes"},
                    {"name": "scott", "debut_season": 1,
                     "age_group": "adult", "now_dead": "no"},
                    {"name": "max", "debut_season": 2,
                     "age_group": "kid", "now_dead": "no"}]}


def json_stream(data):
    stream = StringIO()
    json.dump(data, stream)
    stream.seek(0)
    return stream


@known_failure_githubci_win
def test_extract():
    info, subpaths = au.extract(
        ST_DATA["rows"],
        url_format="{name}_{debut_season}.com",
        filename_format="{age_group}//{now_dead}//{name}.csv")

    eq_(subpaths,
        ["adult", "kid", op.join("adult", "no"), op.join("adult", "yes"), op.join("kid", "no")])

    eq_([d["url"] for d in info],
        ["will_1.com", "bob_2.com", "scott_1.com", "max_2.com"])

    eq_([d["filename"] for d in info],
        [op.join("kid", "no", "will.csv"), op.join("adult", "yes", "bob.csv"),
         op.join("adult", "no", "scott.csv"), op.join("kid", "no", "max.csv")])

    expects = [{"name": "will", "age_group": "kid", "debut_season": "1",
                "now_dead": "no"},
               {"name": "bob", "age_group": "adult", "debut_season": "2",
                "now_dead": "yes"},
               {"name": "scott", "age_group": "adult", "debut_season": "1",
                "now_dead": "no"},
               {"name": "max", "age_group": "kid", "debut_season": "2",
                "now_dead": "no"}]
    for d, expect in zip(info, expects):
        assert_dict_equal(d["meta_args"], expect)

    eq_([d["subpath"] for d in info],
        [op.join("kid", "no"), op.join("adult", "yes"), op.join("adult", "no"), op.join("kid", "no")])


def test_extract_disable_autometa():
    info, _ = au.extract(
        ST_DATA["rows"],
        url_format="{name}_{debut_season}.com",
        filename_format="{age_group}//{now_dead}//{name}.csv",
        exclude_autometa="*",
        meta=["group={age_group}"])

    eq_([d["meta_args"] for d in info],
        [{"group": "kid"}, {"group": "adult"}, {"group": "adult"},
         {"group": "kid"}])


def test_extract_exclude_autometa_regexp():
    info, _ = au.extract(
        ST_DATA["rows"],
        url_format="{name}_{debut_season}.com",
        filename_format="{age_group}//{now_dead}//{name}.csv",
        exclude_autometa="ea")

    expects = [{"name": "will", "age_group": "kid"},
               {"name": "bob", "age_group": "adult"},
               {"name": "scott", "age_group": "adult"},
               {"name": "max", "age_group": "kid"}]
    for d, expect in zip(info, expects):
        assert_dict_equal(d["meta_args"], expect)


@pytest.mark.parametrize("input_type", ["csv", "tsv"])
def test_extract_csv_json_equal(input_type):
    delim = "\t" if input_type == "tsv" else ","

    keys = ST_DATA["header"]
    csv_rows = [delim.join(keys)]
    csv_rows.extend(delim.join(str(row[k]) for k in keys)
                    for row in ST_DATA["rows"])

    kwds = dict(filename_format="{age_group}//{now_dead}//{name}.csv",
                url_format="{name}_{debut_season}.com",
                meta=["group={age_group}"])

    json_output = au.extract(
        *au._read(json_stream(ST_DATA["rows"]), "json"), **kwds)
    csv_output = au.extract(
        *au._read(csv_rows, input_type), **kwds)

    eq_(json_output, csv_output)


def test_extract_wrong_input_type():
    assert_raises(ValueError,
                  au._read, None, "invalid_input_type")


@with_tempfile(mkdir=True)
def test_registerurl_constructor(path=None):
    ds = Dataset(path).create(force=True, annex=True)
    au.RegisterUrl(ds)


@with_tempfile(mkdir=True)
def test_addurls_nonannex_repo(path=None):
    ds = Dataset(path).create(force=True, annex=False)
    with assert_raises(IncompleteResultsError) as raised:
        ds.addurls("dummy_arg0", "dummy_arg1", "dummy_arg2",
                   result_renderer='disabled')
    assert_in("not an annex repo", str(raised.value))


@with_tree({"in.csv": "linky,abcd\nhttps://datalad.org,f"})
def test_addurls_unknown_placeholder(path=None):
    ds = Dataset(path).create(force=True)
    # Close but wrong URL placeholder
    with assert_raises(IncompleteResultsError) as exc:
        ds.addurls("in.csv", "{link}", "{abcd}", dry_run=True,
                   result_renderer='disabled')
    assert_in("linky", str(exc.value))
    # Close but wrong file name placeholder
    with assert_raises(IncompleteResultsError) as exc:
        ds.addurls("in.csv", "{linky}", "{abc}", dry_run=True,
                   result_renderer='disabled')
    assert_in("abcd", str(exc.value))
    # Out-of-bounds index.
    with assert_raises(IncompleteResultsError) as exc:
        ds.addurls("in.csv", "{linky}", "{3}", dry_run=True,
                   result_renderer='disabled')
    assert_in("index", str(exc.value))

    # Suggestions also work for automatic file name placeholders
    with assert_raises(IncompleteResultsError) as exc:
        ds.addurls("in.csv", "{linky}", "{_url_hostnam}", dry_run=True,
                   result_renderer='disabled')
    assert_in("_url_hostname", str(exc.value))
    # ... though if you whiff on the beginning prefix, we don't suggest
    # anything because we decide to generate those fields based on detecting
    # the prefix.
    with assert_raises(IncompleteResultsError) as exc:
        ds.addurls("in.csv", "{linky}", "{_uurl_hostnam}", dry_run=True,
                   result_renderer='disabled')
    assert_not_in("_url_hostname", str(exc.value))


@with_tempfile(mkdir=True)
def test_addurls_dry_run(path=None):
    ds = Dataset(path).create(force=True)

    json_file = "links.json"
    with open(op.join(ds.path, json_file), "w") as jfh:
        json.dump([{"url": "URL/a.dat", "name": "a", "subdir": "foo"},
                   {"url": "URL/b.dat", "name": "b", "subdir": "bar"},
                   {"url": "URL/c.dat", "name": "c", "subdir": "foo"}],
                  jfh)

    ds.save(message="setup")

    with swallow_logs(new_level=logging.INFO) as cml:
        ds.addurls(json_file,
                   "{url}",
                   "{subdir}//{_url_filename_root}",
                   dry_run=True, result_renderer='disabled')

        for dir_ in ["foo", "bar"]:
            assert_in("Would create a subdataset at {}".format(dir_),
                      cml.out)
        assert_in(
            "Would download URL/a.dat to {}".format(
                os.path.join(path, "foo", "BASE")),
            cml.out)

        assert_in("Metadata: {}".format([u"name=a", u"subdir=foo"]),
                  cml.out)


OLD_EXAMINEKEY = external_versions["cmd:annex"] < "8.20201116"
skip_key_tests = skip_if(
    OLD_EXAMINEKEY,
    "git-annex version does not support `examinekey --migrate-to-backend`")


class TestAddurls(object):

    @classmethod
    def setup_class(cls):
        mktmp_kws = get_tempfile_kwargs()
        path = tempfile.mkdtemp(**mktmp_kws)
        http_root = op.join(path, "srv")
        create_tree(http_root,
                    {"udir": {x + ".dat" + ver: x + " content"
                              for x in "abcd"
                              for ver in ["", ".v1"]}})

        cls._hpath = HTTPPath(http_root)
        cls._hpath.start()
        cls.url = cls._hpath.url

        cls.data = [{"url": cls.url + "udir/a.dat",
                     "name": "a",
                     "subdir": "foo",
                     "md5sum": "3fb7c40c70b0ed19da713bd69ee12014",
                     "size": "9"},
                    {"url": cls.url + "udir/b.dat",
                     "name": "b",
                     "subdir": "bar",
                     "md5sum": "",
                     "size": ""},
                    {"url": cls.url + "udir/c.dat",
                     "name": "c",
                     "subdir": "foo",
                     "md5sum": "9b72648021b70b8c522642e4490d7ac3",
                     "size": "9"}]
        cls.json_file = op.join(path, "test_addurls.json")
        with open(cls.json_file, "w") as jfh:
            json.dump(cls.data, jfh)

        cls.temp_dir = path

    @classmethod
    def teardown_class(cls):
        cls._hpath.stop()
        rmtemp(cls.temp_dir)

    @with_tempfile(mkdir=True)
    def test_addurls(self=None, path=None):
        ds = Dataset(path).create(force=True)

        def get_annex_commit_counts():
            return len(ds.repo.get_revisions("git-annex"))

        n_annex_commits = get_annex_commit_counts()

        # Meanwhile also test that we can specify path relative
        # to the top of the dataset, as we generally treat paths in
        # Python API, and it will be the one saved in commit
        # message record
        json_file = op.relpath(self.json_file, ds.path)

        ds.addurls(json_file, "{url}", "{name}",
                   exclude_autometa="(md5sum|size)", result_renderer='disabled')
        ok_startswith(ds.repo.format_commit('%b', DEFAULT_BRANCH), f"url_file='{json_file}'")

        filenames = ["a", "b", "c"]
        for fname in filenames:
            ok_exists(op.join(ds.path, fname))

        for (fname, meta), subdir in zip(ds.repo.get_metadata(filenames),
                                         ["foo", "bar", "foo"]):
            assert_dict_equal(meta,
                              {"subdir": [subdir], "name": [fname]})

        # Ignore this check if we're faking dates because that disables
        # batch mode.
        # Also ignore if on Windows as it seems as if a git-annex bug
        # leads to separate meta data commits:
        # https://github.com/datalad/datalad/pull/5202#discussion_r535429704
        if not (dl_cfg.get('datalad.fake-dates') or on_windows):
            # We should have two new commits on the git-annex: one for the
            # added urls and one for the added metadata.
            eq_(n_annex_commits + 2, get_annex_commit_counts())

        # Add to already existing links, overwriting.
        with swallow_logs(new_level=logging.DEBUG) as cml:
            ds.addurls(self.json_file, "{url}", "{name}",
                       ifexists="overwrite", result_renderer='disabled')
            for fname in filenames:
                assert_in("Removing {}".format(os.path.join(path, fname)),
                          cml.out)

        # Add to already existing links, skipping.
        assert_in_results(
            ds.addurls(self.json_file, "{url}", "{name}", ifexists="skip",
                       result_renderer='disabled'),
            action="addurls",
            status="notneeded")

        # Add to already existing links works, as long content is the same.
        ds.addurls(self.json_file, "{url}", "{name}", result_renderer='disabled')

        # But it fails if something has changed.
        ds.unlock("a")
        with open(op.join(ds.path, "a"), "w") as ofh:
            ofh.write("changed")
        ds.save("a")

        assert_raises(IncompleteResultsError,
                      ds.addurls,
                      self.json_file, "{url}", "{name}",
                      result_renderer='disabled')

    @with_tempfile(mkdir=True)
    def test_addurls_unbound_dataset(self=None, path=None):
        def check(ds, dataset_arg, url_file, fname_format):
            subdir = op.join(ds.path, "subdir")
            os.mkdir(subdir)
            with chpwd(subdir):
                shutil.copy(self.json_file, "in.json")
                addurls(url_file, "{url}", fname_format,
                        dataset=dataset_arg,
                        result_renderer='disabled')
                # Files specified in the CSV file are always relative to the
                # dataset.
                for fname in ["a", "b", "c"]:
                    ok_exists(op.join(ds.path, fname))

        # The input file is relative to the current working directory, as
        # with other commands.
        ds0 = Dataset(op.join(path, "ds0")).create()
        check(ds0, None, "in.json", "{name}")
        # Likewise the input file is relative to the current working directory
        # if a string dataset argument is given.
        ds1 = Dataset(op.join(path, "ds1")).create()
        check(ds1, ds1.path, "in.json", "{name}")
        # A leading "./" doesn't confuse addurls() into downloading the file
        # into the subdirectory.
        ds2 = Dataset(op.join(path, "ds2")).create()
        check(ds2, None, "in.json", "./{name}")

    @with_tempfile(mkdir=True)
    def test_addurls_create_newdataset(self=None, path=None):
        dspath = os.path.join(path, "ds")
        addurls(self.json_file, "{url}", "{name}",
                dataset=dspath,
                cfg_proc=["yoda"], result_renderer='disabled')
        for fname in ["a", "b", "c", "code"]:
            ok_exists(os.path.join(dspath, fname))

    @with_tempfile
    def test_addurls_from_list(self=None, path=None):
        ds = Dataset(path).create()
        ds.addurls(self.data, "{url}", "{name}", result_renderer='disabled')
        for fname in ["a", "b", "c"]:
            ok_exists(op.join(path, fname))

    @with_tempfile(mkdir=True)
    def test_addurls_subdataset(self=None, path=None):
        ds = Dataset(path).create(force=True)

        for save in True, False:
            label = "save" if save else "nosave"
            with swallow_outputs() as cmo:
                ds.addurls(self.json_file, "{url}",
                           "{subdir}-" + label + "//{name}",
                           save=save,
                           cfg_proc=["yoda"])
                # The custom result renderer transforms the subdataset
                # action=create results into something more informative than
                # "create(ok): . (dataset)"...
                assert_in("create(ok): foo-{} (dataset)".format(label),
                          cmo.out)
                # ... and that doesn't lose the standard summary.
                assert_in("create (ok: 2)", cmo.out)

            subdirs = [op.join(ds.path, "{}-{}".format(d, label))
                       for d in ["foo", "bar"]]
            subdir_files = dict(zip(subdirs, [["a", "c"], ["b"]]))

            for subds, fnames in subdir_files.items():
                for fname in fnames:
                    ok_exists(op.join(subds, fname))
                # cfg_proc was applied generated subdatasets.
                ok_exists(op.join(subds, "code"))
            if save:
                assert_repo_status(path)
            else:
                # The datasets are create but not saved (since asked not to)
                assert_repo_status(path, untracked=subdirs)
                # but the downloaded files aren't.
                for subds, fnames in subdir_files.items():
                    assert_repo_status(subds, added=fnames)

        # Now save the "--nosave" changes and check that we have
        # all the subdatasets.
        ds.save()
        eq_(set(subdatasets(dataset=ds, recursive=True,
                            result_xfm="relpaths")),
            {"foo-save", "bar-save", "foo-nosave", "bar-nosave"})

        # We don't try to recreate existing subdatasets.
        with swallow_logs(new_level=logging.DEBUG) as cml:
            ds.addurls(self.json_file, "{url}", "{subdir}-nosave//{name}",
                       result_renderer='disabled')
            assert_in("Not creating subdataset at existing path", cml.out)

    @with_tempfile(mkdir=True)
    def test_addurls_repindex(self=None, path=None):
        ds = Dataset(path).create(force=True)

        with assert_raises(IncompleteResultsError) as raised:
            ds.addurls(self.json_file, "{url}", "{subdir}",
                       result_renderer='disabled')
        assert_in("collided", str(raised.value))

        ds.addurls(self.json_file, "{url}", "{subdir}-{_repindex}",
                   result_renderer='disabled')

        for fname in ["foo-0", "bar-0", "foo-1"]:
            ok_exists(op.join(ds.path, fname))

    @with_tempfile(mkdir=True)
    def test_addurls_url_on_collision_error_if_different(self=None, path=None):
        ds = Dataset(path).create(force=True)

        data = [self.data[0].copy(), self.data[0].copy()]
        data[0]["some_metadata"] = "1"
        data[1]["some_metadata"] = "2"

        with patch("sys.stdin", new=StringIO(json.dumps(data))):
            assert_in_results(
                ds.addurls("-", "{url}", "{name}", on_failure="ignore"),
                action="addurls",
                status="error")

        with patch("sys.stdin", new=StringIO(json.dumps(data))):
            assert_in_results(
                ds.addurls("-", "{url}", "{name}",
                           on_collision="error-if-different",
                           on_failure="ignore"),
                action="addurls",
                status="error")

        with patch("sys.stdin", new=StringIO(json.dumps(data))):
            ds.addurls("-", "{url}", "{name}",
                       exclude_autometa="*",
                       on_collision="error-if-different")
        ok_exists(op.join(ds.path, "a"))

    @with_tempfile(mkdir=True)
    def test_addurls_url_on_collision_choose(self=None, path=None):
        ds = Dataset(path).create(force=True)
        data = deepcopy(self.data)
        for row in data:
            row["name"] = "a"

        with patch("sys.stdin", new=StringIO(json.dumps(data))):
            assert_in_results(
                ds.addurls("-", "{url}", "{name}", on_failure="ignore"),
                action="addurls",
                status="error")
        with patch("sys.stdin", new=StringIO(json.dumps(data))):
            assert_in_results(
                ds.addurls("-", "{url}", "{name}",
                           on_collision="error-if-different",
                           on_failure="ignore"),
                action="addurls",
                status="error")

        with patch("sys.stdin", new=StringIO(json.dumps(data))):
            ds.addurls("-", "{url}", "{name}-first",
                       on_collision="take-first")
        ok_file_has_content(op.join(ds.path, "a-first"), "a content",
                            strip=True)

        with patch("sys.stdin", new=StringIO(json.dumps(data))):
            ds.addurls("-", "{url}", "{name}-last",
                       on_collision="take-last")
        ok_file_has_content(op.join(ds.path, "a-last"), "c content",
                            strip=True)

    @with_tempfile(mkdir=True)
    def test_addurls_url_parts(self=None, path=None):
        ds = Dataset(path).create(force=True)
        ds.addurls(self.json_file, "{url}", "{_url0}/{_url_basename}",
                   result_renderer='disabled')

        for fname in ["a.dat", "b.dat", "c.dat"]:
            ok_exists(op.join(ds.path, "udir", fname))

    @with_tempfile(mkdir=True)
    def test_addurls_url_filename(self=None, path=None):
        ds = Dataset(path).create(force=True)
        ds.addurls(self.json_file, "{url}", "{_url0}/{_url_filename}",
                   result_renderer='disabled')
        for fname in ["a.dat", "b.dat", "c.dat"]:
            ok_exists(op.join(ds.path, "udir", fname))

    @with_tempfile(mkdir=True)
    def test_addurls_url_filename_fail(self=None, path=None):
        ds = Dataset(path).create(force=True)
        assert_raises(IncompleteResultsError,
                      ds.addurls,
                      self.json_file,
                      "{url}/nofilename/",
                      "{_url0}/{_url_filename}",
                      result_renderer='disabled')

    @with_tempfile(mkdir=True)
    def test_addurls_url_special_key_fail(self=None, path=None):
        ds = Dataset(path).create(force=True)

        res1 = ds.addurls(self.json_file, "{url}", "{_url4}/{_url_filename}",
                          on_failure="ignore", result_renderer='disabled')
        assert_in("Special key", res1[0]["message"])

        data = self.data.copy()[:1]
        data[0]["url"] = urlparse(data[0]["url"]).netloc
        with patch("sys.stdin", new=StringIO(json.dumps(data))):
            res2 = ds.addurls("-", "{url}", "{_url_basename}",
                              on_failure="ignore", result_renderer='disabled')
        assert_in("Special key", res2[0]["message"])

    @with_tempfile(mkdir=True)
    def test_addurls_metafail(self=None, path=None):
        ds = Dataset(path).create(force=True)

        # Force failure by passing a non-existent file name to annex.
        fn = ds.repo.set_metadata_

        def set_meta(_, **kwargs):
            for i in fn("wreaking-havoc-and-such", **kwargs):
                yield i

        with patch.object(ds.repo, 'set_metadata_', set_meta):
            with assert_raises(IncompleteResultsError):
                ds.addurls(self.json_file, "{url}", "{name}",
                           result_renderer='disabled')

    @with_tempfile(mkdir=True)
    def test_addurls_dropped_urls(self=None, path=None):
        ds = Dataset(path).create(force=True)
        with swallow_logs(new_level=logging.WARNING) as cml:
            ds.addurls(self.json_file, "", "{subdir}//{name}",
                       result_renderer='disabled')
            assert_re_in(r".*Dropped [0-9]+ row\(s\) that had an empty URL",
                         str(cml.out))

    @with_tempfile(mkdir=True)
    def test_addurls_version(self=None, path=None):
        ds = Dataset(path).create(force=True)

        def version_fn(url):
            if url.endswith("b.dat"):
                raise ValueError("Scheme error")
            return url + ".v1"

        with patch("datalad.local.addurls.get_versioned_url", version_fn):
            with swallow_logs(new_level=logging.WARNING) as cml:
                ds.addurls(self.json_file, "{url}", "{name}",
                           version_urls=True, result_renderer='disabled')
                assert_in("b.dat", str(cml.out))

        names = ["a", "c"]
        for fname in names:
            ok_exists(os.path.join(path, fname))

        whereis = ds.repo.whereis(names, output="full")
        for fname, info in whereis.items():
            eq_(info[WEB_SPECIAL_REMOTE_UUID]['urls'],
                ["{}udir/{}.dat.v1".format(self.url, fname)])

    @with_tempfile(mkdir=True)
    def test_addurls_deeper(self=None, path=None):
        ds = Dataset(path).create(force=True)
        ds.addurls(
            self.json_file, "{url}",
            "{subdir}//adir/{subdir}-again//other-ds//bdir/{name}",
            jobs=3, result_renderer='disabled')
        eq_(set(ds.subdatasets(recursive=True, result_xfm="relpaths")),
            {"foo",
             "bar",
             op.join("foo", "adir", "foo-again"),
             op.join("bar", "adir", "bar-again"),
             op.join("foo", "adir", "foo-again", "other-ds"),
             op.join("bar", "adir", "bar-again", "other-ds")})
        ok_exists(os.path.join(
            ds.path, "foo", "adir", "foo-again", "other-ds", "bdir", "a"))

    @with_tree({"in": ""})
    def test_addurls_invalid_input(self=None, path=None):
        ds = Dataset(path).create(force=True)
        in_file = op.join(path, "in")
        for in_type in au.INPUT_TYPES:
            with assert_raises(IncompleteResultsError) as exc:
                ds.addurls(in_file, "{url}", "{name}", input_type=in_type,
                           result_renderer='disabled')
            assert_in("Failed to read", str(exc.value))

    @with_tree({"in.csv": "url,name,subdir",
                "in.tsv": "url\tname\tsubdir",
                "in.json": "[]"})
    def test_addurls_no_rows(self=None, path=None):
        ds = Dataset(path).create(force=True)
        for fname in ["in.csv", "in.tsv", "in.json"]:
            with swallow_logs(new_level=logging.WARNING) as cml:
                assert_in_results(
                    ds.addurls(fname, "{url}", "{name}", result_renderer='disabled'),
                    action="addurls",
                    status="notneeded")
                cml.assert_logged("No rows", regex=False)

    @with_tempfile(mkdir=True)
    def check_addurls_stdin_input(self, input_text, input_type, path):
        ds = Dataset(path).create(force=True)
        with patch("sys.stdin", new=StringIO(input_text)):
            ds.addurls("-", "{url}", "{name}", input_type=input_type,
                       result_renderer='disabled')
        for fname in ["a", "b", "c"]:
            ok_exists(op.join(ds.path, fname))

    def test_addurls_stdin_input(self=None):
        with open(self.json_file) as jfh:
            json_text = jfh.read()

        self.check_addurls_stdin_input(json_text, "ext")
        self.check_addurls_stdin_input(json_text, "json")

        def make_delim_text(delim):
            row = "{name}" + delim + "{url}"
            return "\n".join(
                [row.format(name="name", url="url")] +
                [row.format(**rec) for rec in json.loads(json_text)])

        self.check_addurls_stdin_input(make_delim_text(","), "csv")
        self.check_addurls_stdin_input(make_delim_text("\t"), "tsv")

    @with_tempfile(mkdir=True)
    def test_addurls_stdin_input_command_line(self=None, path=None):
        # The previous test checks all the cases, but it overrides sys.stdin.
        # Do a simple check that's closer to a command line call.
        Dataset(path).create(force=True)
        runner = WitlessRunner(cwd=path)
        with open(self.json_file) as jfh:
            runner.run(["datalad", "addurls", '-', '{url}', '{name}'],
                       stdin=jfh)
        for fname in ["a", "b", "c"]:
            ok_exists(op.join(path, fname))

    @with_tempfile(mkdir=True)
    def test_drop_after(self=None, path=None):
        ds = Dataset(path).create(force=True)
        ds.repo.set_gitattributes([('a*', {'annex.largefiles': 'nothing'})])
        # make some files go to git, so we could test that we do not blow
        # while trying to drop what is in git not annex
        res = ds.addurls(self.json_file, '{url}', '{name}', drop_after=True,
                         result_renderer='disabled')

        assert_result_count(res, 3, action='addurl', status='ok')  # a, b, c  even if a goes to git
        assert_result_count(res, 2, action='drop', status='ok')  # b, c

    @with_tempfile(mkdir=True)
    def test_addurls_from_key_invalid_format(self=None, path=None):
        ds = Dataset(path).create(force=True)
        for fmt in ["{name}-which-has-no-double-dash",
                    # Invalid hash length.
                    "MD5-s{size}--{md5sum}a",
                    # Invalid hash content.
                    "MD5-s{size}--" + 32 * "q"]:
            with assert_raises(IncompleteResultsError):
                ds.addurls(self.json_file, "{url}", "{name}",
                           key=fmt, exclude_autometa="*",
                           result_renderer='disabled')

    @with_tempfile(mkdir=True)
    def check_addurls_from_key(self, key_arg, expected_backend, fake_dates,
                               path):
        ds = Dataset(path).create(force=True, fake_dates=fake_dates)
        if OLD_EXAMINEKEY and ds.repo.is_managed_branch():
            raise SkipTest("Adjusted branch functionality requires "
                           "more recent `git annex examinekey`")
        ds.addurls(self.json_file, "{url}", "{name}", exclude_autometa="*",
                   key=key_arg, result_renderer='disabled')
        repo = ds.repo
        repo_path = ds.repo.pathobj
        paths = [repo_path / x for x in "ac"]

        annexinfo = repo.get_content_annexinfo(eval_availability=True)
        for path in paths:
            pstat = annexinfo[path]
            eq_(pstat["backend"], expected_backend)
            assert_false(pstat["has_content"])

        get_res = ds.get(paths, result_renderer='disabled', on_failure="ignore")
        assert_result_count(get_res, 2, action="get", status="ok")

    def test_addurls_from_key(self=None):
        fn = self.check_addurls_from_key
        for testfunc, arg1, arg2 in [
                (fn, "MD5-s{size}--{md5sum}", "MD5"),
                (fn, "MD5E-s{size}--{md5sum}.dat", "MD5E"),
                (skip_key_tests(fn), "et:MD5-s{size}--{md5sum}", "MD5E"),
                (skip_key_tests(fn), "et:MD5E-s{size}--{md5sum}.dat", "MD5")]:
            testfunc(arg1, arg2, False)
            testfunc(arg1, arg2, True)

    @with_tempfile(mkdir=True)
    def test_addurls_row_missing_key_fields(self=None, path=None):
        ds = Dataset(path).create(force=True)
        if OLD_EXAMINEKEY and ds.repo.is_managed_branch():
            raise SkipTest("Adjusted branch functionality requires "
                           "more recent `git annex examinekey`")
        data = deepcopy(self.data)
        for row in data:
            if row["name"] == "b":
                del row["md5sum"]
                break
        with patch("sys.stdin", new=StringIO(json.dumps(data))):
            ds.addurls("-", "{url}", "{name}", exclude_autometa="*",
                       key="MD5-s{size}--{md5sum}", result_renderer='disabled')

        repo = ds.repo
        repo_path = ds.repo.pathobj
        paths = [repo_path / x for x in "ac"]

        annexinfo = repo.get_content_annexinfo(eval_availability=True)
        for path in paths:
            pstat = annexinfo[path]
            eq_(pstat["backend"], "MD5")
            assert_false(pstat["has_content"])
