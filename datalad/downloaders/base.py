# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Provide access to stuff (html, data files) via HTTP and HTTPS

"""

__docformat__ = 'restructuredtext'


from ..utils import auto_repr

from logging import getLogger
lgr = getLogger('datalad.downloaders')

class BaseDownloader(object):
    """Base class for the downloaders"""
    pass

# Exceptions.  might migrate elsewhere

class DownloadError(Exception):
    pass

class AccessDeniedError(DownloadError):
    pass

#
# Authenticators    XXX might go into authenticators.py
#

class Authenticator(object):
    """Abstract common class for different types of authentication

    Derived classes should get parameterized with options from the config files
    from "provider:" sections
    """
    requires_authentication = True
    # TODO: figure out interface

    def authenticate(self, *args, **kwargs):
        if self.requires_authentication:
            raise NotImplementedError("Authentication for %s not yet implemented" % self.__class__)

class NotImplementedAuthenticator(Authenticator):
    pass

class NoneAuthenticator(Authenticator):
    """Whenever no authentication is necessary and that is stated explicitly"""
    requires_authentication = False
    pass

