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
from six.moves import StringIO

from datalad.tests.utils import assert_raises
from datalad.plugin import addurls


def test_formatter():
    idx_to_name = {i: "col{}".format(i) for i in range(4)}
    values = {"col{}".format(i): "value{}".format(i) for i in range(4)}

    fmt = addurls.Formatter(idx_to_name)

    fmt.format("{0}", values) == "value0"
    fmt.format("{0}", values) == fmt.format("{col0}", values)

    # Integer placeholders outside of `idx_to_name` don't work.
    assert_raises(KeyError, fmt.format, "{4}", values, 1, 2, 3, 4)

    # If the named placeholder is not in `values`, falls back to normal
    # formatting.
    fmt.format("{notinvals}", values, notinvals="ok") == "ok"


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


def test_clean_meta_args():
    for args, expect in [(["", "field="], []),
                         ([" field=yes "], ["field=yes"]),
                         ([" atag "], ["tag=atag"]),
                         (["field= value="], ["field=value="])]:
        assert list(addurls.clean_meta_args(args)) == expect

    assert_raises(ValueError,
                  list,
                  addurls.clean_meta_args(["=value"]))


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
        "{age_group}//{now_dead}//{name}.csv",
        "{name}_{debut_season}.com",
        ["group={age_group}"])

    assert subpaths == {"kid", "kid/no", "adult", "adult/yes", "adult/no"}

    fnames, urls, meta, subdss = zip(*info)

    assert urls == ("will_1.com", "bob_2.com", "scott_1.com", "max_2.com")

    assert fnames == ("kid/no/will.csv", "adult/yes/bob.csv",
                      "adult/no/scott.csv", "kid/no/max.csv")

    assert meta == (["group=kid"], ["group=adult"],
                    ["group=adult"], ["group=kid"])

    assert subdss == ("kid/no", "adult/yes", "adult/no", "kid/no")


def test_extract_csv_json_equal():
    keys = ST_DATA["header"]
    csv_rows = [",".join(keys)]
    csv_rows.extend(",".join(str(row[k]) for k in keys)
                    for row in ST_DATA["rows"])

    args = ["{age_group}//{now_dead}//{name}.csv",
            "{name}_{debut_season}.com",
            ["group={age_group}"]]

    json_output = addurls.extract(json_stream(ST_DATA["rows"]), "json", *args)
    csv_output = addurls.extract(csv_rows, "csv", *args)

    assert json_output == csv_output


def test_extract_wrong_input_type():
    assert_raises(ValueError,
                  addurls.extract,
                  None, "not_csv_or_json", None, None, None)
