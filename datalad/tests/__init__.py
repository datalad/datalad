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

def setup_module():
    # To overcome pybuild by default defining http{,s}_proxy we would need
    # to define them to e.g. empty value so it wouldn't bother touching them.
    # But then haskell libraries do not digest empty value nicely, so we just
    # pop them out from the environment
    for ev in ('http_proxy', 'https_proxy'):
        if ev in os.environ and not (os.environ[ev]):
            lgr.debug("Removing %s from the environment since it is empty", ev)
            os.environ.pop(ev)

# We will delay generation of some test files/directories until they are
# actually used but then would remove them here
_TEMP_PATHS_GENERATED = []
def teardown_module():
    from datalad.tests.utils import rmtemp
    lgr.debug("Teardown tests. " +
              (("Removing dirs/files: %s" % ', '.join(_TEMP_PATHS_GENERATED))
                if _TEMP_PATHS_GENERATED else "Nothing to remove"))
    for path in _TEMP_PATHS_GENERATED:
        rmtemp(path)

# Give a custom template so we could hunt them down easily
tempfile.template = os.path.join(tempfile.gettempdir(),
                                 'tmp-page2annex')

