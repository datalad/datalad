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

import shutil
import sys
from unittest.mock import patch

# Not really worth to be there but it is ATM, so let's use that
import pytest

from datalad.api import (
    create,
    shell_completion,
)
from datalad.cmd import (
    StdOutErrCapture,
    WitlessRunner,
)
from datalad.support.external_versions import external_versions
from datalad.tests.utils_pytest import (
    assert_cwd_unchanged,
    assert_in,
    eq_,
    skip_if_no_module,
    skip_if_on_windows,
    swallow_outputs,
    with_tempfile,
)


@assert_cwd_unchanged
def test_shell_completion_python():
    skip_if_no_module('argcomplete')
    # largely a smoke test for our print("hello world")
    with swallow_outputs() as cmo:
        res = shell_completion()
        out = cmo.out.rstrip()
    # we get it printed and returned for double-pleasure
    eq_(out, res[0]['content'].rstrip())


@pytest.mark.ai_generated
def test_shell_completion_no_argcomplete():
    # None in sys.modules makes the import fail
    with patch.dict(sys.modules, {'argcomplete': None}), \
            swallow_outputs() as cmo:
        res = shell_completion(on_failure='ignore')
        eq_(cmo.out, '')
    eq_(len(res), 1)
    eq_(res[0]['status'], 'error')
    assert_in('argcomplete failed to import', res[0]['message'][0])


@skip_if_on_windows  # TODO: make it more specific since might work if bash is available
def test_shell_completion_source():
    skip_if_no_module('argcomplete')
    # just smoke test that produced shell script sources nicely without error
    WitlessRunner().run(['bash', '-c', 'source <(datalad shell-completion)'])
    # ideally we should feed that shell with TAB to see the result of completion but
    # yoh sees no easy way ATM, and googled up
    # https://stackoverflow.com/questions/9137245/unit-test-for-bash-completion-script
    # requires too much enthusiasm toward this goal.


@pytest.mark.ai_generated
@skip_if_on_windows
def test_shell_completion_source_zsh():
    skip_if_no_module('argcomplete')
    if not shutil.which('zsh'):
        pytest.skip("no zsh")
    # -f: no startup files, so the completion system is not initialized yet
    out = WitlessRunner().run(
        ['zsh', '-f', '-c',
         'source <(datalad shell-completion) && print -r -- $_comps[datalad]'],
        protocol=StdOutErrCapture)['stdout']
    # registered natively, not via bashcompinit
    eq_(out.strip(), '_python_argcomplete')


@pytest.mark.ai_generated
@skip_if_on_windows
@with_tempfile(mkdir=True)
def test_shell_completion_function(path=None):
    skip_if_no_module('argcomplete')
    ds = create(path, annex=False)
    ds.repo.add_remote('origin', 'https://example.com/origin')

    def complete(line):
        """Return what the completion function replies to bash for `line`"""
        out = WitlessRunner(cwd=path).run(
            ['bash', '-c',
             # not "source <(...)": bash 3.2, still the stock one on macOS,
             # loads nothing from a process substitution
             'eval "$(datalad shell-completion)"; '
             'COMP_LINE=$1; COMP_POINT=${#COMP_LINE}; '
             '_python_argcomplete datalad; '
             'printf "%s\\n" "${COMPREPLY[@]}"',
             '_', line],
            protocol=StdOutErrCapture)['stdout']
        return out.splitlines()

    eq_(complete('datalad push --to o'), ['origin '])
    eq_(complete('datalad push --to=o'), ['origin '])
    # the quote of the value being completed is not closed yet
    eq_(complete('datalad push --to "o'), ['origin'])
    eq_(complete("datalad push --to 'o"), ['origin'])
    if external_versions['argcomplete'] >= '3.8.0':
        # older argcomplete replies with "--to=origin", which bash places
        # after the quote
        eq_(complete('datalad push --to="o'), ['origin'])
