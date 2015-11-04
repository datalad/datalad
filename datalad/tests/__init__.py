# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

import os
import shutil
import tempfile
from logging import getLogger

lgr = getLogger("datalad.tests")

# We will delay generation of some test files/directories until they are
# actually used but then would remove them here
_TEMP_PATHS_GENERATED = []

# Give a custom template so we could hunt them down easily
tempfile.template = os.path.join(tempfile.gettempdir(),
                                 'tmp-page2annex')

