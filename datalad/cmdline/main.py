# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""
.. deprecated:: 0.16
   datalad.cmdline.main was replaced by datalad.cli.main
"""

import warnings
warnings.warn("datalad.cmdline.main was replaced by datalad.cli.main in "
              "datalad 0.16. Please update and reinstall extensions.",
              DeprecationWarning)

from datalad.cli.main import main
from datalad.cli.parser import setup_parser
