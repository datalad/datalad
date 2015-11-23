# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Sub-module to provide access (as to download/query etc) to the remote sites

"""

__docformat__ = 'restructuredtext'

from six.moves.urllib.parse import urlparse


from .providers import Providers

from logging import getLogger
lgr = getLogger('datalad.providers')

# TODO: we might not need to instantiate it right here
# lgr.debug("Initializing data providers credentials interface")
# providers = Providers().from_config_files()