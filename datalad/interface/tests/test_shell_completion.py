# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""test command datalad shell_completion

"""

__docformat__ = 'restructuredtext'

# Not really worth to be there but it is ATM, so let's use that
from datalad.api import shell_completion
from datalad.cmd import WitlessRunner
from datalad.tests.utils_pytest import (
    assert_cwd_unchanged,
    eq_,
    skip_if_on_windows,
    swallow_outputs,
)


@assert_cwd_unchanged
def test_shell_completion_python():
    # largely a smoke test for our print("hello world")
    with swallow_outputs() as cmo:
        res = shell_completion()
        out = cmo.out.rstrip()
    # we get it printed and returned for double-pleasure
    eq_(out, res[0]['content'].rstrip())


@skip_if_on_windows  # TODO: make it more specific since might work if bash is available
def test_shell_completion_source():
    # just smoke test that produced shell script sources nicely without error
    WitlessRunner().run(['bash', '-c', 'source <(datalad shell-completion)'])
    # ideally we should feed that shell with TAB to see the result of completion but
    # yoh sees no easy way ATM, and googled up
    # https://stackoverflow.com/questions/9137245/unit-test-for-bash-completion-script
    # requires too much enthusiasm toward this goal.
