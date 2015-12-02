# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""tests for dialog UI """

__docformat__ = 'restructuredtext'

from six import PY2
from six.moves import StringIO
import six.moves.builtins as __builtin__

from mock import patch
from ...tests.utils import eq_
from ...tests.utils import assert_raises
from ...tests.utils import assert_re_in
from ...tests.utils import assert_in
from ...tests.utils import ok_startswith
from ...tests.utils import ok_endswith
from ..dialog import DialogUI

def patch_input(**kwargs):
    """A helper to provide mocked cm patching input function which was renamed in PY3"""
    return patch.object(__builtin__, 'raw_input' if PY2 else 'input', **kwargs)

def test_question_choices():

    # TODO: come up with a reusable fixture for testing here

    choices = {
        'a': '[a], b, cc',
        'b': 'a, [b], cc',
        'cc': 'a, b, [cc]'
    }

    for default_value in ['a', 'b']:
        choices_str = choices[default_value]
        for entered_value, expected_value in [(default_value, default_value),
                                              ('', default_value),
                                              ('cc', 'cc')]:
            with patch_input(return_value=entered_value):
                out = StringIO()
                response = DialogUI(out=out).question("prompt", choices=sorted(choices), default=default_value)
                eq_(response, expected_value)
                eq_(out.getvalue(), 'prompt (choices: %s): ' % choices_str)

    # check some expected exceptions to be thrown
    out = StringIO()
    ui = DialogUI(out=out)
    assert_raises(ValueError, ui.question, "prompt", choices=['a'], default='b')
    eq_(out.getvalue(), '')

    with patch_input(return_value='incorrect'):
        assert_raises(RuntimeError, ui.question, "prompt", choices=['a', 'b'])
    assert_re_in(".*prompt.*ERROR: .incorrect. is not among choices.*", out.getvalue())


def _test_progress_bar(len):
    out = StringIO()
    fill_str = ('123456890' * (len//10))[:len]
    pb = DialogUI(out).get_progressbar('label', fill_str, maxval=10)
    pb.start()
    for x in range(11):
        pb.update(x)
        out.flush()  # needed atm
        pstr = out.getvalue()
        ok_startswith(pstr, 'label:')
        assert_in(' %d%% ' % (10*x), pstr)
        assert_in('ETA', pstr)
    pb.finish()
    ok_endswith(out.getvalue(), '\n')

def test_progress_bar():
    # More of smoke testing given various lengths of fill_text
    yield _test_progress_bar, 0
    yield _test_progress_bar, 4
    yield _test_progress_bar, 10
    yield _test_progress_bar, 1000