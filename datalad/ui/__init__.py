# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Interactive User Interface (as Dialog/GUI/etc) support

"""

__docformat__ = 'restructuredtext'

from .dialog import ConsoleLog, DialogUI
from ..utils import is_interactive


# TODO: implement logic on selection of the ui based on the cfg and environment
# e.g. we cannot use DialogUI if session is not interactive
# TODO:  GitAnnexUI where interactive queries (such as question) should get to the
# user by proxying some other appropriate (cmdline or GUI) UI, while others, such
# as reporting on progress etc -- should get back to the annex
if not is_interactive():
    ui = ConsoleLog()
else:
    ui = DialogUI()