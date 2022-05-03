# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""test the holy grail of interfaces

"""

from datalad.cmd import (
    StdOutCapture,
    WitlessRunner,
)
from datalad.tests.utils_pytest import (
    assert_in,
    assert_not_in,
    eq_,
    ok_,
    swallow_outputs,
    with_tempfile,
)

from ..base import update_docstring_with_parameters


@with_tempfile(mkdir=True)
def test_status_custom_summary_no_repeats(path=None):
    from datalad.api import Dataset
    from datalad.core.local.status import Status

    # This regression test depends on the command having a custom summary
    # renderer *and* the particular call producing summary output. status()
    # having this method doesn't guarantee that it is still an appropriate
    # command for this test, but it's at least a necessary condition.
    ok_(hasattr(Status, "custom_result_summary_renderer"))

    ds = Dataset(path).create()
    out = WitlessRunner(cwd=path).run(
        ["datalad", "--output-format=tailored", "status"],
        protocol=StdOutCapture)
    out_lines = out['stdout'].splitlines()
    ok_(out_lines)
    eq_(len(out_lines), len(set(out_lines)))

    with swallow_outputs() as cmo:
        ds.status(return_type="list", result_renderer="tailored")
        eq_(out_lines, cmo.out.splitlines())


def test_update_docstring_with_parameters_no_kwds():
    from datalad.support.param import Parameter

    def fn(pos0):
        "fn doc"

    assert_not_in("3", fn.__doc__)
    # Call doesn't crash when there are no keyword arguments.
    update_docstring_with_parameters(
        fn,
        dict(pos0=Parameter(doc="pos0 param doc"),
             pos1=Parameter(doc="pos1 param doc")),
        add_args={"pos1": 3})
    assert_in("3", fn.__doc__)


def test_update_docstring_with_parameters_single_line_prefix():
    from datalad.support.param import Parameter

    def fn(pos0, pos1):
        pass

    update_docstring_with_parameters(
        fn,
        dict(pos0=Parameter(doc="pos0 param doc"),
             pos1=Parameter(doc="pos1 param doc")),
        prefix="This is a single line.",
    )
    assert_in("This is a single line.\n\nParameters\n", fn.__doc__)
