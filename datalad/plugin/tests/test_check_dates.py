# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

from functools import partial
import json
import logging
import os

from datalad.api import create, Dataset
from datalad.support.exceptions import IncompleteResultsError
from datalad.support.tests.test_repodates import set_date
from datalad.tests.utils import assert_dict_equal, assert_false, assert_in, \
    assert_raises, eq_, ok_, create_tree, with_tempfile, with_tree
from datalad.utils import chpwd, swallow_logs, swallow_outputs

from datalad.plugin import check_dates

call = partial(check_dates.CheckDates.__call__,
               result_renderer="disabled",
               return_type="list")


@with_tree(tree={"invalid": {".git": {}}})
def test_check_dates_invalid_repo(path):
    with swallow_logs(new_level=logging.WARNING) as cml:
        call(paths=[path])
        cml.assert_logged("Skipping invalid")


def test_check_dates_invalid_date():
    with swallow_outputs() as cmo:
        assert_raises(IncompleteResultsError,
                      check_dates.CheckDates.__call__,
                      [],
                      reference_date="not a valid date",
                      return_type="list")
        out = cmo.out
    # The error makes it through the standard renderer.
    assert_in('"status": "error"', out)


@with_tempfile(mkdir=True)
def test_check_dates(path):
    ref_ts = 1218182889  # Fri, 08 Aug 2008 04:08:09 -0400
    refdate = "@{}".format(ref_ts)

    repo0 = os.path.join(path, "repo0")
    create(repo0)
    create_tree(repo0, {"a": "a"})

    with set_date(ref_ts + 5000):
        Dataset(repo0).add(".")

    # The standard renderer outputs json.
    with swallow_outputs() as cmo:
        check_dates.CheckDates.__call__(
            [],
            reference_date=refdate,
            return_type="list")
        assert_in("report", json.loads(cmo.out).keys())

    # We find the newer objects.
    newer = call([path], reference_date=refdate)
    eq_(len(newer), 1)
    ok_(newer[0]["report"]["objects"])

    # There are no older objects to find.
    older = call([repo0], reference_date=refdate, older=True)
    assert_false(older[0]["report"]["objects"])

    # We can pass the date in RFC 2822 format.
    assert_dict_equal(
        newer[0],
        call([path], reference_date="08 Aug 2008 04:08:09 -0400")[0])

    # paths=None defaults to the current directory.
    with chpwd(path):
        assert_dict_equal(newer[0],
                          call(paths=None, reference_date=refdate)[0])

    # Only commit type is present when annex='none'.
    newer_noannex = call([path], reference_date=refdate, annex="none")
    for entry in newer_noannex[0]["report"]["objects"].values():
        ok_(entry["type"] == "commit")
