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

def test_UI_Switcher():
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