# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Interface information about credentials

Provides minimalistic interface to deal (query, request, store) with most common
types of credentials.  To be used by Authenticators
"""

__dev_doc__ = """
Possibly useful in the future 3rd part developments

https://github.com/omab/python-social-auth
    social authentication/registration mechanism with support for several
    frameworks and auth providers
"""

from collections import OrderedDict

from ..dochelpers import exc_str
from ..support.keyring_ import keyring as keyring_
from ..ui import ui
from ..utils import auto_repr

from logging import getLogger
lgr = getLogger('datalad.downloaders.credentials')


@auto_repr
class Credential(object):
    """Base class for different types of credentials
    """

    # Should be defined in a subclass as an OrderedDict of fields
    # name -> dict(attributes) where currently a single attribute 'hidden' is used
    # to signal if value should be hidden by UI while entering
    _FIELDS = None

    def __init__(self, name, url=None, keyring=None):
        """
        Parameters
        ----------
        name : str
            Name of the credential, as it would be identified by in the centralized
            storage of credentials
        url : str, optional
            URL string to point users to where to seek obtaining the credentials
        keyring : a keyring
            An object providing (g|s)et_password.  If None, keyring module is used
            as is
        """
        self.name = name
        self.url = url
        self._keyring = keyring or keyring_

    def _ask_field_value(self, f, hidden=False):
        return ui.question(
            f,
            title="You need to authenticate with %r credentials." % self.name +
                  " %s provides information on how to gain access"
                  % self.url if self.url else '',
            hidden=hidden)

    @property
    def is_known(self):
        """Return True if values for all fields of the credential are known"""
        try:
            return all(self._keyring.get(self.name, f) is not None
                       for f in self._FIELDS)
        except Exception as exc:
            lgr.warning("Failed to query keyring: %s" % exc_str(exc))
            return False

    def enter_new(self):
        """Enter new values for the credential fields"""
        # Use ui., request credential fields corresponding to the type
        for f, fopts in self._FIELDS.items():
            v = self._ask_field_value(f, **fopts)
            self._keyring.set(self.name, f, v)

    def __call__(self):
        """Obtain credentials from a keyring and if any is not known -- ask"""
        name = self.name
        fields = {}
        for f, fopts in self._FIELDS.items():
            v = self._keyring.get(name, f)
            while v is None:  # was not known
                v = self._ask_field_value(f, **fopts)
                self._keyring.set(name, f, v)
            fields[f] = v
        return fields


class UserPassword(Credential):
    """Simple type of a credential which consists of user/password pair"""

    _FIELDS = OrderedDict([('user', {}), ('password', {'hidden': True})])


class AWS_S3(Credential):
    """Credential for AWS S3 service"""

    _FIELDS = OrderedDict([('key_id', {}), ('secret_id', {'hidden': True})])


CREDENTIAL_TYPES = {
    'user_password': UserPassword,
    'aws-s3': AWS_S3,
}
