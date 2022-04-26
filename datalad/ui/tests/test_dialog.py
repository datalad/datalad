# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""tests for dialog UI """

__docformat__ = 'restructuredtext'

import builtins
from io import StringIO
from unittest.mock import (
    call,
    patch,
)

import pytest

from datalad.ui.progressbars import progressbars
from datalad.utils import swallow_logs

from ...tests.utils_pytest import (
    assert_in,
    assert_not_in,
    assert_raises,
    assert_re_in,
    eq_,
    ok_endswith,
    ok_startswith,
)
from ..dialog import (
    ConsoleLog,
    DialogUI,
    IPythonUI,
)


def patch_input(**kwargs):
    """A helper to provide mocked cm patching input function which was renamed in PY3"""
    return patch.object(builtins, 'input', **kwargs)


def patch_getpass(**kwargs):
    return patch('getpass.getpass', **kwargs)


def test_yesno():
    for expected_value, defaults in {True: ('yes', True),
                                     False: ('no', False)}.items():
        for d in defaults:
            with patch_getpass(return_value=''):
                out = StringIO()
                response = DialogUI(out=out).yesno("?", default=d)
                eq_(response, expected_value)


def test_question_choices():

    # TODO: come up with a reusable fixture for testing here

    choices = {
        'a': '[a], b, cc',
        'b': 'a, [b], cc',
        'cc': 'a, b, [cc]'
    }

    for hidden in (True, False):
        for default_value in ['a', 'b']:
            choices_str = choices[default_value]
            for entered_value, expected_value in [(default_value, default_value),
                                                  ('', default_value),
                                                  ('cc', 'cc')]:
                with patch_getpass(return_value=entered_value) as gpcm:
                    out = StringIO()
                    response = DialogUI(out=out).question(
                        "prompt", choices=sorted(choices), default=default_value,
                        hidden=hidden
                    )
                    # .assert_called_once() is not available on older mock's
                    # e.g. on  1.3.0 on nd16.04
                    eq_(gpcm.call_count, 1)  # should have asked only once
                    eq_(response, expected_value)
                    # getpass doesn't use out -- goes straight to the terminal
                    eq_(out.getvalue(), '')
                    # TODO: may be test that the prompt was passed as a part of the getpass arg
                    #eq_(out.getvalue(), 'prompt (choices: %s): ' % choices_str)

    # check some expected exceptions to be thrown
    out = StringIO()
    ui = DialogUI(out=out)
    assert_raises(ValueError, ui.question, "prompt", choices=['a'], default='b')
    eq_(out.getvalue(), '')

    with patch_getpass(return_value='incorrect'):
        assert_raises(RuntimeError, ui.question, "prompt", choices=['a', 'b'])
    assert_re_in(".*ERROR: .incorrect. is not among choices.*", out.getvalue())


def test_hidden_doubleentry():
    # In above test due to 'choices' there were no double entry for a hidden
    out = StringIO()
    ui = DialogUI(out=out)
    with patch_getpass(return_value='ab') as gpcm:
        response = ui.question(
            "?", hidden=True)
        eq_(response, 'ab')
        gpcm.assert_has_calls([call('?: '), call('? (repeat): ')])

    # explicitly request no repeats
    with patch_getpass(return_value='ab') as gpcm:
        response = ui.question(
            "?", hidden=True, repeat=False)
        eq_(response, 'ab')
        gpcm.assert_has_calls([call('?: ')])


@pytest.mark.parametrize("backend", progressbars)
@pytest.mark.parametrize("len", [0, 4, 10, 1000])
@pytest.mark.parametrize("increment", [True, False])
def test_progress_bar(backend, len, increment):
    # More of smoke testing given various lengths of fill_text
    out = StringIO()
    fill_str = ('123456890' * (len//10))[:len]
    pb = DialogUI(out).get_progressbar(
        'label', fill_str, total=10, backend=backend)
    pb.start()
    # we can't increment 11 times
    SILENT_BACKENDS = ('annex-remote', 'silent', 'none')
    ONLY_THE_END_BACKENDS = ('log',)
    for x in range(11):
        if not (increment and x == 0):
            # do not increment on 0
            pb.update(x if not increment else 1, increment=increment)
        #out.flush()  # needed atm... no longer?
        # Progress bar is having 0.1 sec between updates by default, so
        # we could either sleep:
        #import time; time.sleep(0.1)
        # or just force the refresh
        pb.refresh()
        pstr = out.getvalue()
        if backend not in SILENT_BACKENDS + ONLY_THE_END_BACKENDS:  # no str repr
            ok_startswith(pstr.lstrip('\r'), 'label:')
            assert_re_in(r'.*\b%d%%.*' % (10*x), pstr)
        if backend == 'progressbar':
            assert_in('ETA', pstr)
    pb.finish()
    output = out.getvalue()
    if backend not in SILENT_BACKENDS:
        # returns back and there is no spurious newline
        if output:
            ok_endswith(output, '\r')


def test_IPythonUI():
    # largely just smoke tests to see if nothing is horribly bad
    with patch_input(return_value='a'):
        out = StringIO()
        response = IPythonUI(out=out).question(
            "prompt", choices=sorted(['b', 'a'])
        )
        eq_(response, 'a')
        eq_(out.getvalue(), 'prompt (choices: a, b): ')

    ui = IPythonUI()
    pbar = ui.get_progressbar(total=10)
    assert_in('notebook', str(pbar._tqdm))


def test_silent_question():
    # SilentConsoleLog must not be asked questions.
    # If it is asked, RuntimeError would be thrown with details to help
    # troubleshooting WTF is happening
    from ..dialog import SilentConsoleLog
    ui = SilentConsoleLog()
    with assert_raises(RuntimeError) as cme:
        ui.question("could you help me", title="Pretty please")
    assert_in('question: could you help me. Title: Pretty please.', str(cme.value))

    with assert_raises(RuntimeError) as cme:
        ui.question("could you help me", title="Pretty please", choices=['secret1'], hidden=True)
    assert_in('question: could you help me. Title: Pretty please.', str(cme.value))
    assert_not_in('secret1', str(cme.value))
    assert_in('not shown', str(cme.value))

    # additional kwargs, no title, choices
    with assert_raises(RuntimeError) as cme:
        ui.question("q", choices=['secret1'])
    assert_in('secret1', str(cme.value))


@patch("datalad.log.is_interactive", lambda: False)
def test_message_pbar_state_logging_is_demoted():
    from datalad.log import LoggerHelper

    name = "dl-test"
    lgr = LoggerHelper(name).get_initialized_logger()
    ui = ConsoleLog()

    with patch("datalad.ui.dialog.lgr", lgr):
        with swallow_logs(name=name, new_level=20) as cml:
            ui.message("testing 0")
            assert_not_in("Clear progress bars", cml.out)
            assert_not_in("Refresh progress bars", cml.out)
        with swallow_logs(name=name, new_level=5) as cml:
            ui.message("testing 1")
            assert_in("Clear progress bars", cml.out)
            assert_in("Refresh progress bars", cml.out)
