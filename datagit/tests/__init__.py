#emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
#ex: set sts=4 ts=4 sw=4 noet:

__author__ = 'Yaroslav Halchenko'
__copyright__ = 'Copyright (c) 2013 Yaroslav Halchenko'
__license__ = 'MIT'

import os
import tempfile

# Give a custom template so we could hunt them down easily
tempfile.template = os.path.join(tempfile.gettempdir(),
                                 'tmp-page2annex')
print "TEMPLATE:", tempfile.template
