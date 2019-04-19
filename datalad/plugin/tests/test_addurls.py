# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# -*- coding: utf-8 -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test addurls plugin"""

import json
import logging
import os
import tempfile

from mock import patch

from six.moves import StringIO

from datalad.api import addurls, Dataset, subdatasets
import datalad.plugin.addurls as au
from datalad.support.exceptions import IncompleteResultsError
from datalad.tests.utils import chpwd, slow, swallow_logs
from datalad.tests.utils import assert_false, assert_true, assert_raises
from datalad.tests.utils import assert_in, assert_re_in, assert_in_results
from datalad.tests.utils import assert_dict_equal
from datalad.tests.utils import eq_, ok_exists
from datalad.tests.utils import create_tree, with_tempfile, HTTPPath
from datalad.utils import get_tempfile_kwargs, rmtemp


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
    assert_raises(ValueError, fmt.format, "{0}", "not a mapping")


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
    for fname, expect in [("no/dbl/slash", ("no/dbl/slash", [])),
                          ("p1//n", ("p1/n", ["p1"])),
                          ("p1//p2/p3//n", ("p1/p2/p3/n",
                                            ["p1", "p1/p2/p3"])),
                          ("//n", ("/n", [""])),
                          ("n//", ("n/", ["n"]))]:
        eq_(au.get_subpaths(fname), expect)


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


def test_extract():
    info, subpaths = au.extract(
        json_stream(ST_DATA["rows"]), "json",
        url_format="{name}_{debut_season}.com",
        filename_format="{age_group}//{now_dead}//{name}.csv")

    eq_(subpaths,
        {"kid", "kid/no", "adult", "adult/yes", "adult/no"})

    eq_([d["url"] for d in info],
        ["will_1.com", "bob_2.com", "scott_1.com", "max_2.com"])

    eq_([d["filename"] for d in info],
        ["kid/no/will.csv", "adult/yes/bob.csv",
         "adult/no/scott.csv", "kid/no/max.csv"])

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
        ["kid/no", "adult/yes", "adult/no", "kid/no"])


def test_extract_disable_autometa():
    info, _ = au.extract(
        json_stream(ST_DATA["rows"]), "json",
        url_format="{name}_{debut_season}.com",
        filename_format="{age_group}//{now_dead}//{name}.csv",
        exclude_autometa="*",
        meta=["group={age_group}"])

    eq_([d["meta_args"] for d in info],
        [{"group": "kid"}, {"group": "adult"}, {"group": "adult"},
         {"group": "kid"}])


def test_extract_exclude_autometa_regexp():
    info, _ = au.extract(
        json_stream(ST_DATA["rows"]), "json",
        url_format="{name}_{debut_season}.com",
        filename_format="{age_group}//{now_dead}//{name}.csv",
        exclude_autometa="ea")

    expects = [{"name": "will", "age_group": "kid"},
               {"name": "bob", "age_group": "adult"},
               {"name": "scott", "age_group": "adult"},
               {"name": "max", "age_group": "kid"}]
    for d, expect in zip(info, expects):
        assert_dict_equal(d["meta_args"], expect)


def test_extract_csv_json_equal():
    keys = ST_DATA["header"]
    csv_rows = [",".join(keys)]
    csv_rows.extend(",".join(str(row[k]) for k in keys)
                    for row in ST_DATA["rows"])

    kwds = dict(filename_format="{age_group}//{now_dead}//{name}.csv",
                url_format="{name}_{debut_season}.com",
                meta=["group={age_group}"])

    json_output = au.extract(json_stream(ST_DATA["rows"]), "json", **kwds)
    csv_output = au.extract(csv_rows, "csv", **kwds)

    eq_(json_output, csv_output)


def test_extract_wrong_input_type():
    assert_raises(ValueError,
                  au.extract, None, "not_csv_or_json")


@with_tempfile(mkdir=True)
def test_addurls_nonannex_repo(path):
    ds = Dataset(path).create(force=True, no_annex=True)
    with assert_raises(IncompleteResultsError) as raised:
        ds.addurls("dummy_arg0", "dummy_arg1", "dummy_arg2")
    assert_in("not an annex repo", str(raised.exception))


@with_tempfile(mkdir=True)
def test_addurls_dry_run(path):
    ds = Dataset(path).create(force=True)

    with chpwd(path):
        json_file = "links.json"
        with open(json_file, "w") as jfh:
            json.dump([{"url": "URL/a.dat", "name": "a", "subdir": "foo"},
                       {"url": "URL/b.dat", "name": "b", "subdir": "bar"},
                       {"url": "URL/c.dat", "name": "c", "subdir": "foo"}],
                      jfh)

        ds.add(".", message="setup")

        with swallow_logs(new_level=logging.INFO) as cml:
            ds.addurls(json_file,
                       "{url}",
                       "{subdir}//{_url_filename_root}",
                       dry_run=True)

            for dir_ in ["foo", "bar"]:
                assert_in("Would create a subdataset at {}".format(dir_),
                          cml.out)
            assert_in(
                "Would download URL/a.dat to {}".format(
                    os.path.join(path, "foo", "BASE")),
                cml.out)

            assert_in("Metadata: {}".format([u"name=a", u"subdir=foo"]),
                      cml.out)


@slow  # ~9s
class TestAddurls(object):

    @classmethod
    def setup_class(cls):
        mktmp_kws = get_tempfile_kwargs()
        path = tempfile.mkdtemp(**mktmp_kws)
        create_tree(path,
                    {"udir": {x + ".dat" + ver: x + " content"
                              for x in "abcd"
                              for ver in ["", ".v1"]}})

        cls._hpath = HTTPPath(path)
        cls._hpath.start()
        cls.url = cls._hpath.url

        cls.json_file = tempfile.mktemp(suffix=".json", **mktmp_kws)
        with open(cls.json_file, "w") as jfh:
            json.dump(
                [{"url": cls.url + "udir/a.dat", "name": "a", "subdir": "foo"},
                 {"url": cls.url + "udir/b.dat", "name": "b", "subdir": "bar"},
                 {"url": cls.url + "udir/c.dat", "name": "c", "subdir": "foo"}],
                jfh)

    @classmethod
    def teardown_class(cls):
        cls._hpath.stop()
        rmtemp(cls._hpath.path)

    @with_tempfile(mkdir=True)
    def test_addurls(self, path):
        ds = Dataset(path).create(force=True)

        def get_annex_commit_counts():
            return int(
                ds.repo.repo.git.rev_list("--count", "git-annex").strip())

        n_annex_commits = get_annex_commit_counts()

        with chpwd(path):
            ds.addurls(self.json_file, "{url}", "{name}")

            filenames = ["a", "b", "c"]
            for fname in filenames:
                ok_exists(fname)

            for (fname, meta), subdir in zip(ds.repo.get_metadata(filenames),
                                             ["foo", "bar", "foo"]):
                assert_dict_equal(meta,
                                  {"subdir": [subdir], "name": [fname]})

            # Ignore this check if we're faking dates because that disables
            # batch mode.
            if not os.environ.get('DATALAD_FAKE__DATES'):
                # We should have two new commits on the git-annex: one for the
                # added urls and one for the added metadata.
                eq_(n_annex_commits + 2, get_annex_commit_counts())

            # Add to already existing links, overwriting.
            with swallow_logs(new_level=logging.DEBUG) as cml:
                ds.addurls(self.json_file, "{url}", "{name}",
                           ifexists="overwrite")
                for fname in filenames:
                    assert_in("Removing {}".format(os.path.join(path, fname)),
                              cml.out)

            # Add to already existing links, skipping.
            assert_in_results(
                ds.addurls(self.json_file, "{url}", "{name}", ifexists="skip"),
                action="addurls",
                status="notneeded")

            # Add to already existing links works, as long content is the same.
            ds.addurls(self.json_file, "{url}", "{name}")

            # But it fails if something has changed.
            ds.unlock("a")
            with open("a", "w") as ofh:
                ofh.write("changed")
            ds.add("a")

            assert_raises(IncompleteResultsError,
                          ds.addurls,
                          self.json_file, "{url}", "{name}")

    @with_tempfile(mkdir=True)
    def test_addurls_create_newdataset(self, path):
        dspath = os.path.join(path, "ds")
        addurls(dspath, self.json_file, "{url}", "{name}")
        for fname in ["a", "b", "c"]:
            ok_exists(os.path.join(dspath, fname))

    @with_tempfile(mkdir=True)
    def test_addurls_subdataset(self, path):
        ds = Dataset(path).create(force=True)

        with chpwd(path):
            for save in True, False:
                label = "save" if save else "nosave"
                hexsha_before = ds.repo.get_hexsha()
                ds.addurls(self.json_file, "{url}",
                           "{subdir}-" + label + "//{name}",
                           save=save)
                hexsha_after = ds.repo.get_hexsha()

                for fname in ["foo-{}/a", "bar-{}/b", "foo-{}/c"]:
                    ok_exists(fname.format(label))

                assert_true(save ^ (hexsha_before == hexsha_after))
                assert_true(save ^ ds.repo.dirty)

            # Now save the "--nosave" changes and check that we have
            # all the subdatasets.
            ds.add(".")
            eq_(set(subdatasets(ds, recursive=True,
                                result_xfm="relpaths")),
                {"foo-save", "bar-save", "foo-nosave", "bar-nosave"})

            # We don't try to recreate existing subdatasets.
            with swallow_logs(new_level=logging.DEBUG) as cml:
                ds.addurls(self.json_file, "{url}", "{subdir}-nosave//{name}")
                assert_in("Not creating subdataset at existing path", cml.out)

    @with_tempfile(mkdir=True)
    def test_addurls_repindex(self, path):
        ds = Dataset(path).create(force=True)

        with chpwd(path):
            with assert_raises(IncompleteResultsError) as raised:
                ds.addurls(self.json_file, "{url}", "{subdir}")
            assert_in("There are file name collisions", str(raised.exception))

            ds.addurls(self.json_file, "{url}", "{subdir}-{_repindex}")

            for fname in ["foo-0", "bar-0", "foo-1"]:
                ok_exists(fname)

    @with_tempfile(mkdir=True)
    def test_addurls_url_parts(self, path):
        ds = Dataset(path).create(force=True)
        with chpwd(path):
            ds.addurls(self.json_file, "{url}", "{_url0}/{_url_basename}")

            for fname in ["udir/a.dat", "udir/b.dat", "udir/c.dat"]:
                ok_exists(fname)

    @with_tempfile(mkdir=True)
    def test_addurls_url_filename(self, path):
        ds = Dataset(path).create(force=True)
        with chpwd(path):
            ds.addurls(self.json_file, "{url}", "{_url0}/{_url_filename}")
            for fname in ["udir/a.dat", "udir/b.dat", "udir/c.dat"]:
                ok_exists(fname)

    @with_tempfile(mkdir=True)
    def test_addurls_url_filename_fail(self, path):
        ds = Dataset(path).create(force=True)
        with chpwd(path):
            assert_raises(IncompleteResultsError,
                          ds.addurls,
                          self.json_file,
                          "{url}/nofilename/",
                          "{_url0}/{_url_filename}")

    @with_tempfile(mkdir=True)
    def test_addurls_metafail(self, path):
        ds = Dataset(path).create(force=True)

        # Force failure by passing a non-existent file name to annex.
        fn = ds.repo.set_metadata

        def set_meta(_, **kwargs):
            for i in fn("wreaking-havoc-and-such", **kwargs):
                yield i

        with chpwd(path), patch.object(ds.repo, 'set_metadata', set_meta):
            with assert_raises(IncompleteResultsError):
                ds.addurls(self.json_file, "{url}", "{name}")

    @with_tempfile(mkdir=True)
    def test_addurls_dropped_urls(self, path):
        ds = Dataset(path).create(force=True)
        with chpwd(path), swallow_logs(new_level=logging.WARNING) as cml:
            ds.addurls(self.json_file, "", "{subdir}//{name}")
            assert_re_in(r".*Dropped [0-9]+ row\(s\) that had an empty URL",
                         str(cml.out))

    @with_tempfile(mkdir=True)
    def test_addurls_version(self, path):
        ds = Dataset(path).create(force=True)

        def version_fn(url):
            if url.endswith("b.dat"):
                raise ValueError("Scheme error")
            return url + ".v1"

        with patch("datalad.plugin.addurls.get_versioned_url", version_fn):
            with swallow_logs(new_level=logging.WARNING) as cml:
                ds.addurls(self.json_file, "{url}", "{name}",
                           version_urls=True)
                assert_in("b.dat", str(cml.out))

        names = ["a", "c"]
        for fname in names:
            ok_exists(os.path.join(path, fname))

        whereis = ds.repo.whereis(names, output="full")
        for fname, info in whereis.items():
            eq_(info[ds.repo.WEB_UUID]['urls'],
                ["{}udir/{}.dat.v1".format(self.url, fname)])
