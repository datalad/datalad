# emacs: -*- mode: python; py-indent-offset: 4; tab-wstrth: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""tests for UI switcher"""

__docformat__ = 'restructuredtext'

from .. import _UI_Switcher
from ..dialog import DialogUI, ConsoleLog
from ...tests.utils import assert_equal, assert_not_equal
from ...tests.utils import assert_raises
from ...tests.utils import assert_false
from ...tests.utils import with_testsui


def test_ui_switcher():
    ui = _UI_Switcher('dialog')
    assert(isinstance(ui.ui, DialogUI))
    message_str = str(ui.message)
    assert_equal(message_str, str(ui._ui.message))

    ui.set_backend('console')
    assert(isinstance(ui.ui, ConsoleLog))
    assert_equal(str(ui.message), str(ui._ui.message))
    assert_not_equal(message_str, str(ui._ui.message))
    with assert_raises(AttributeError):
        ui.yesno

    ui.set_backend('annex')


def test_tests_ui():
    ui = _UI_Switcher('dialog')
    # Let's test our responses construct
    ui.set_backend('tests')
    with ui.add_responses('abc'):
        assert_equal(ui.question("text"), 'abc')

    with ui.add_responses(['a', 'bb']):
        assert_equal(ui.question("text"), 'a')
        assert_equal(ui.question("text"), 'bb')

    # should raise exception if not all responses were
    # used
    with assert_raises(AssertionError):
        with ui.add_responses(['a', 'bb']):
            assert_equal(ui.question("text"), 'a')

    # but clear it up
    assert_false(ui.get_responses())

    # assure that still works
    with ui.add_responses('abc'):
        assert_equal(ui.question("text"), 'abc')

    # and if we switch back to some other backend -- we would loose *responses methods
    ui.set_backend('annex')
    assert_false(hasattr(ui, 'add_responses'))


def test_with_testsui():

    @with_testsui
    def nothing(x, k=1):
        assert_equal(x, 1)
        assert_equal(k, 2)

    nothing(1, k=2)

    @with_testsui(responses='a')
    def nothing(x, k=1):
        assert_equal(x, 1)
        assert_equal(k, 2)

    # responses were not used
    assert_raises(AssertionError, nothing, 1, k=2)

    from datalad.ui import ui

    @with_testsui(responses='a')
    def ask():
        assert_equal(ui.question('what is a?'), 'a')
