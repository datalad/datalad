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

from six.moves import StringIO

from mock import patch
from ...tests.utils import eq_
from ...tests.utils import assert_raises
from ...tests.utils import assert_re_in
from ..dialog import DialogUI

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
            with patch('__builtin__.raw_input', return_value=entered_value):
                out = StringIO()
                response = DialogUI(out=out).question("prompt", choices=sorted(choices), default=default_value)
                eq_(response, expected_value)
                eq_(out.getvalue(), 'prompt (choices: %s): ' % choices_str)

    # check some expected exceptions to be thrown
    out = StringIO()
    ui = DialogUI(out=out)
    assert_raises(ValueError, ui.question, "prompt", choices=['a'], default='b')
    eq_(out.getvalue(), '')

    with patch('__builtin__.raw_input', return_value='incorrect'):
        assert_raises(RuntimeError, ui.question, "prompt", choices=['a', 'b'])
    assert_re_in(".*prompt.*ERROR: .incorrect. is not among choices.*", out.getvalue())