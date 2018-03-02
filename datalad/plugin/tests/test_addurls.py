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

from six.moves import StringIO

from datalad.api import Dataset, plugin, subdatasets
from datalad.support.exceptions import IncompleteResultsError
from datalad.tests.utils import chpwd, slow, swallow_logs
from datalad.tests.utils import assert_false, assert_true, assert_raises
from datalad.tests.utils import assert_in, assert_in_results, assert_dict_equal
from datalad.tests.utils import eq_, ok_exists
from datalad.tests.utils import create_tree, with_tree, with_tempfile, HTTPPath
from datalad.utils import get_tempfile_kwargs, rmtemp

from datalad.plugin import addurls


def test_formatter():
    idx_to_name = {i: "col{}".format(i) for i in range(4)}
    values = {"col{}".format(i): "value{}".format(i) for i in range(4)}

    fmt = addurls.Formatter(idx_to_name)

    eq_(fmt.format("{0}", values), "value0")
    eq_(fmt.format("{0}", values), fmt.format("{col0}", values))

    # Integer placeholders outside of `idx_to_name` don't work.
    assert_raises(KeyError, fmt.format, "{4}", values, 1, 2, 3, 4)

    # If the named placeholder is not in `values`, falls back to normal
    # formatting.
    eq_(fmt.format("{notinvals}", values, notinvals="ok"), "ok")


def test_formatter_lower_case():
    fmt = addurls.Formatter({0: "key"})
    eq_(fmt.format("{key!l}", {"key": "UP"}), "up")
    eq_(fmt.format("{0!l}", {"key": "UP"}), "up")
    eq_(fmt.format("{other!s}", {}, other=[1, 2]), "[1, 2]")


def test_formatter_no_idx_map():
    fmt = addurls.Formatter({})
    assert_raises(KeyError, fmt.format, "{0}", {"col0": "value0"})


def test_formatter_no_mapping_arg():
    fmt = addurls.Formatter({})
    assert_raises(ValueError, fmt.format, "{0}", "not a mapping")


def test_formatter_placeholder_with_spaces():
    fmt = addurls.Formatter({})
    fmt.format("{with spaces}", {"with spaces": "value0"}) == "value0"


def test_formatter_placeholder_nonpermitted_chars():
    fmt = addurls.Formatter({})

    # Can't assess keys with !, which will be interpreted as a conversion flag.
    fmt.format("{key!r}", {"key!r": "value0"}, key="x") == "x"
    assert_raises(KeyError,
                  fmt.format, "{key!r}", {"key!r": "value0"})

    # Same for ":".
    fmt.format("{key:<5}", {"key:<5": "value0"}, key="x") == "x    "
    assert_raises(KeyError,
                  fmt.format, "{key:<5}", {"key:<5": "value0"})


def test_formatter_missing_arg():
    fmt = addurls.Formatter({}, "NA")
    eq_(fmt.format("{here},{nothere}", {"here": "ok", "nothere": ""}),
        "ok,NA")


def test_repformatter():
    fmt = addurls.RepFormatter({})

    for i in range(3):
        eq_(fmt.format("{c}{_repindex}", {"c": "x"}), "x{}".format(i))
    # A new result gets a fresh index.
    for i in range(2):
        eq_(fmt.format("{c}{_repindex}", {"c": "y"}), "y{}".format(i))
    # We count even if _repindex isn't there.
    eq_(fmt.format("{c}", {"c": "z0"}), "z0")
    eq_(fmt.format("{c}{_repindex}", {"c": "z"}), "z1")


def test_clean_meta_args():
    for args, expect in [(["field="], []),
                         ([" field=yes "], ["field=yes"]),
                         (["field= value="], ["field=value="])]:
        eq_(list(addurls.clean_meta_args(args)), expect)

    assert_raises(ValueError,
                  list,
                  addurls.clean_meta_args(["noequal"]))
    assert_raises(ValueError,
                  list,
                  addurls.clean_meta_args(["=value"]))


def test_get_subpaths():
    for fname, expect in [("no/dbl/slash", ("no/dbl/slash", [])),
                          ("p1//n", ("p1/n", ["p1"])),
                          ("p1//p2/p3//n", ("p1/p2/p3/n",
                                            ["p1", "p1/p2/p3"])),
                          ("//n", ("/n", [""])),
                          ("n//", ("n/", ["n"]))]:
        eq_(addurls.get_subpaths(fname), expect)


def test_is_legal_metafield():
    for legal in ["legal", "0", "legal_"]:
        assert_true(addurls.is_legal_metafield(legal))
    for notlegal in ["_not", "with space"]:
        assert_false(addurls.is_legal_metafield(notlegal))


def test_filter_legal_metafield():
    eq_(addurls.filter_legal_metafield(["legal", "_not", "legal_still"]),
        ["legal", "legal_still"])


def test_fmt_to_name():
    eq_(addurls.fmt_to_name("{name}", {}), "name")
    eq_(addurls.fmt_to_name("{0}", {0: "name"}), "name")
    eq_(addurls.fmt_to_name("{1}", {0: "name"}), "1")

    assert_false(addurls.fmt_to_name("frontmatter{name}", {}))
    assert_false(addurls.fmt_to_name("{name}backmatter", {}))
    assert_false(addurls.fmt_to_name("{two}{names}", {}))
    assert_false(addurls.fmt_to_name("", {}))
    assert_false(addurls.fmt_to_name("nonames", {}))
    assert_false(addurls.fmt_to_name("{}", {}))


def test_get_url_names():
    eq_(addurls.get_url_names(""), {})
    eq_(addurls.get_url_names("http://datalad.org"), {})

    assert_dict_equal(addurls.get_url_names("http://datalad.org/about.html"),
                      {"_url0": "about.html",
                       "_url_basename": "about.html"})
    assert_dict_equal(addurls.get_url_names("http://datalad.org/about.html"),
                      addurls.get_url_names("http://datalad.org//about.html"))

    assert_dict_equal(
        addurls.get_url_names("http://datalad.org/for/git-users"),
        {"_url0": "for",
         "_url1": "git-users",
         "_url_basename": "git-users"})


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
    info, subpaths = addurls.extract(
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

    eq_([set(d["meta_args"]) for d in info],
        [{"name=will", "age_group=kid", "debut_season=1", "now_dead=no"},
         {"name=bob", "age_group=adult", "debut_season=2", "now_dead=yes"},
         {"name=scott", "age_group=adult", "debut_season=1", "now_dead=no"},
         {"name=max", "age_group=kid", "debut_season=2", "now_dead=no"}])

    eq_([d["subpath"] for d in info],
        ["kid/no", "adult/yes", "adult/no", "kid/no"])


def test_extract_disable_autometa():
    info, subpaths = addurls.extract(
        json_stream(ST_DATA["rows"]), "json",
        url_format="{name}_{debut_season}.com",
        filename_format="{age_group}//{now_dead}//{name}.csv",
        exclude_autometa="*",
        meta=["group={age_group}"])


    eq_([d["meta_args"] for d in info],
        [["group=kid"], ["group=adult"], ["group=adult"], ["group=kid"]])


def test_extract_exclude_autometa_regexp():
    info, subpaths = addurls.extract(
        json_stream(ST_DATA["rows"]), "json",
        url_format="{name}_{debut_season}.com",
        filename_format="{age_group}//{now_dead}//{name}.csv",
        exclude_autometa="ea")

    eq_([set(d["meta_args"]) for d in info],
        [{"name=will", "age_group=kid"},
         {"name=bob", "age_group=adult"},
         {"name=scott", "age_group=adult"},
         {"name=max", "age_group=kid"}])

def test_extract_csv_json_equal():
    keys = ST_DATA["header"]
    csv_rows = [",".join(keys)]
    csv_rows.extend(",".join(str(row[k]) for k in keys)
                    for row in ST_DATA["rows"])

    kwds = dict(filename_format="{age_group}//{now_dead}//{name}.csv",
                url_format="{name}_{debut_season}.com",
                meta=["group={age_group}"])


    json_output = addurls.extract(json_stream(ST_DATA["rows"]), "json", **kwds)
    csv_output = addurls.extract(csv_rows, "csv", **kwds)

    eq_(json_output, csv_output)


def test_extract_wrong_input_type():
    assert_raises(ValueError,
                  addurls.extract, None, "not_csv_or_json")


def test_addurls_no_urlfile():
    with assert_raises(IncompleteResultsError) as raised:
        plugin("addurls")
    assert_in("Must specify url_file argument", str(raised.exception))


@with_tempfile(mkdir=True)
def test_addurls_nonannex_repo(path):
    ds = Dataset(path).create(force=True, no_annex=True)
    with assert_raises(IncompleteResultsError) as raised:
        ds.plugin("addurls", url_file="dummy")
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
            ds.plugin("addurls", url_file=json_file, url_format="{url}",
                      filename_format="{subdir}//{name}", dry_run=True)

            for dir_ in ["foo", "bar"]:
                assert_in("Would create a subdataset at {}".format(dir_),
                          cml.out)
            assert_in(
                "Would download URL/a.dat to {}".format(
                    os.path.join(path, "foo", "a")),
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
                    {"udir": {x + ".dat": x + " content" for x in "abcd"}})

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

        with chpwd(path):
            ds.plugin("addurls", url_file=self.json_file,
                      url_format="{url}", filename_format="{name}")

            filenames = ["a", "b", "c"]
            for fname in filenames:
                ok_exists(fname)

            meta_results = dict(
                zip(filenames,
                    ds.repo._run_annex_command_json("metadata",
                                                    files=filenames)))

            for fname, subdir in zip(filenames, ["foo", "bar", "foo"]):
                assert_dict_equal(
                    {k: v for k, v in meta_results[fname]["fields"].items()
                     if not k.endswith("lastchanged")},
                    {"subdir": [subdir], "name": [fname]})

            # Add to already existing links, overwriting.
            with swallow_logs(new_level=logging.DEBUG) as cml:
                ds.plugin("addurls", url_file=self.json_file,
                          url_format="{url}", filename_format="{name}",
                          ifexists="overwrite")
                for fname in filenames:
                    assert_in("Removing {}".format(os.path.join(path, fname)),
                              cml.out)

            # Add to already existing links, skipping.
            assert_in_results(
                ds.plugin("addurls", url_file=self.json_file,
                          url_format="{url}", filename_format="{name}",
                          ifexists="skip"),
                action="addurls",
                status="notneeded")

            # Add to already existing links works, as long content is the same.
            ds.plugin("addurls", url_file=self.json_file,
                      url_format="{url}", filename_format="{name}")

            # But it fails if something has changed.
            ds.unlock("a")
            with open("a", "w") as ofh:
                ofh.write("changed")
            ds.add("a")

            assert_raises(IncompleteResultsError,
                          ds.plugin,
                          "addurls", url_file=self.json_file,
                          url_format="{url}", filename_format="{name}")

    @with_tempfile(mkdir=True)
    def test_addurls_create_newdataset(self, path):
        dspath = os.path.join(path, "ds")
        plugin("addurls",
               dataset=dspath,
               url_file=self.json_file,
               url_format="{url}", filename_format="{name}")

        for fname in ["a", "b", "c"]:
            ok_exists(os.path.join(dspath, fname))

    @with_tempfile(mkdir=True)
    def test_addurls_subdataset(self, path):
        ds = Dataset(path).create(force=True)

        with chpwd(path):
            ds.plugin("addurls", url_file=self.json_file,
                      url_format="{url}", filename_format="{subdir}//{name}")

            for fname in ["foo/a", "bar/b", "foo/c"]:
                ok_exists(fname)

            eq_(set(subdatasets(ds, recursive=True, result_xfm="relpaths")),
                {"foo", "bar"})

            # We don't try to recreate existing subdatasets.
            with swallow_logs(new_level=logging.DEBUG) as cml:
                ds.plugin("addurls", url_file=self.json_file,
                          url_format="{url}",
                          filename_format="{subdir}//{name}")
                assert_in("Not creating subdataset at existing path", cml.out)

    @with_tempfile(mkdir=True)
    def test_addurls_repindex(self, path):
        ds = Dataset(path).create(force=True)

        with chpwd(path):
            with assert_raises(IncompleteResultsError) as raised:
                ds.plugin("addurls", url_file=self.json_file,
                          url_format="{url}", filename_format="{subdir}")
            assert_in("There are file name collisions", str(raised.exception))

            ds.plugin("addurls", url_file=self.json_file,
                      url_format="{url}",
                      filename_format="{subdir}-{_repindex}")

            for fname in ["foo-0", "bar-0", "foo-1"]:
                ok_exists(fname)

    @with_tempfile(mkdir=True)
    def test_addurls_url_parts(self, path):
        ds = Dataset(path).create(force=True)
        with chpwd(path):
            ds.plugin("addurls", url_file=self.json_file,
                      url_format="{url}",
                      filename_format="{_url0}/{_url_basename}")

            for fname in ["udir/a.dat", "udir/b.dat", "udir/c.dat"]:
                ok_exists(fname)
