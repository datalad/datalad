# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

import json
import logging
import os
from functools import partial

from datalad.api import check_dates
from datalad.support.annexrepo import AnnexRepo
from datalad.support.exceptions import IncompleteResultsError
from datalad.support.tests.test_repodates import set_date
from datalad.tests.utils_pytest import (
    assert_dict_equal,
    assert_false,
    assert_in,
    assert_raises,
    eq_,
    ok_,
    skip_if_no_module,
    with_tree,
)
from datalad.utils import (
    chpwd,
    swallow_logs,
    swallow_outputs,
)

call = partial(check_dates, result_renderer="disabled", return_type="list")


@with_tree(tree={"invalid": {".git": {}}})
def test_check_dates_invalid_repo(path=None):
    with swallow_logs(new_level=logging.WARNING) as cml:
        call(paths=[path])
        cml.assert_logged("Skipping invalid")


def test_check_dates_invalid_date():
    skip_if_no_module("dateutil")

    with swallow_outputs() as cmo:
        assert_raises(IncompleteResultsError,
                      check_dates, [],
                      reference_date="not a valid date",
                      return_type="list")
        out = cmo.out
    # The error makes it through the standard renderer.
    assert_in('"status": "error"', out)


@with_tree(tree={"repo": {"a": "a"}})
def test_check_dates(path=None):
    skip_if_no_module("dateutil")

    ref_ts = 1218182889  # Fri, 08 Aug 2008 04:08:09 -0400
    refdate = "@{}".format(ref_ts)

    repo = os.path.join(path, "repo")
    with set_date(ref_ts + 5000):
        ar = AnnexRepo(repo)
        ar.add(".")
        ar.commit()

    # The standard renderer outputs json.
    with swallow_outputs() as cmo:
        # Set level to WARNING to avoid the progress bar when
        # DATALAD_TESTS_UI_BACKEND=console.
        with swallow_logs(new_level=logging.WARNING):
            check_dates([repo],
                        reference_date=refdate,
                        return_type="list")
        assert_in("report", json.loads(cmo.out).keys())

    # We find the newer objects.
    newer = call([path], reference_date=refdate)
    eq_(len(newer), 1)
    ok_(newer[0]["report"]["objects"])

    # There are no older objects to find.
    older = call([repo], reference_date=refdate, older=True)
    assert_false(older[0]["report"]["objects"])

    # We can pass the date in RFC 2822 format.
    assert_dict_equal(
        newer[0],
        call([path], reference_date="08 Aug 2008 04:08:09 -0400")[0])

    # paths=None defaults to the current directory.
    with chpwd(path):
        assert_dict_equal(
            newer[0]["report"],
            call(paths=None, reference_date=refdate)[0]["report"])

    # Only commit type is present when annex='none'.
    newer_noannex = call([path], reference_date=refdate, annex="none")
    for entry in newer_noannex[0]["report"]["objects"].values():
        ok_(entry["type"] == "commit")
