# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
# Compatibility kludge for now to not break anything relying on datalad.version
# TODO: announce in 0.15 to be deprecated for 0.16
#

from ._version import get_versions

__version__ = get_versions()['version']
__hardcoded_version__ = __version__
__full_version__ = __version__

del get_versions