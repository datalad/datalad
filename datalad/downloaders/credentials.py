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

import time
import calendar

from collections import OrderedDict

from ..dochelpers import exc_str
from ..support.keyring_ import keyring as keyring_
from ..ui import ui
from ..utils import auto_repr
from ..support.network import iso8601_to_epoch

from logging import getLogger
lgr = getLogger('datalad.downloaders.credentials')


@auto_repr
class Credential(object):
    """Base class for different types of credentials
    """

    # Should be defined in a subclass as an OrderedDict of fields
    # name -> dict(attributes)
    _FIELDS = None
    _KNOWN_ATTRS = {
        'hidden',    # UI should not display the value
        'optional',  # Not mandatory thus not requested if not set
    }

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
        self._prepare()

    def _prepare(self):
        """Additional house-keeping possibly to be performed in subclasses

        Created to avoid all the passing args/kwargs of __init__ all the time
        """
        # Basic checks
        for f, fattrs in self._FIELDS.items():
            unknown_attrs = set(fattrs).difference(self._KNOWN_ATTRS)
            if unknown_attrs:
                raise ValueError("Unknown attributes %s. Known are: %s"
                                 % (unknown_attrs, self._KNOWN_ATTRS))

    def _is_field_optional(self, f):
        return self._FIELDS[f].get('optional', False)

    def _is_field_hidden(self, f):
        return self._FIELDS[f].get('hidden', False)

    @property
    def is_known(self):
        """Return True if values for all fields of the credential are known"""
        try:
            return all(
                self._is_field_optional(f) or self._keyring.get(self.name, f) is not None
                for f in self._FIELDS)
        except Exception as exc:
            lgr.warning("Failed to query keyring: %s" % exc_str(exc))
            return False

    def _ask_field_value(self, f):
        return ui.question(
            f,
            title="You need to authenticate with %r credentials." % self.name +
                  " %s provides information on how to gain access"
                  % self.url if self.url else '',
            hidden=self._is_field_hidden(f))

    def _ask_and_set(self, f):
        v = self._ask_field_value(f)
        self.set(**{f: v})
        return v

    def enter_new(self, **kwargs):
        """Enter new values for the credential fields

        Parameters
        ----------
        **kwargs
          Any given key value pairs with non-None values are used to set the
          field `key` to the given value, without asking for user input
        """
        # Use ui., request credential fields corresponding to the type
        for f in self._FIELDS:
            if kwargs.get(f, None):
                # use given value, don't ask
                self.set(**{f: kwargs[f]})
            elif not self._is_field_optional(f):
                self._ask_and_set(f)

    def __call__(self):
        """Obtain credentials from a keyring and if any is not known -- ask"""
        name = self.name
        fields = {}
        for f in self._FIELDS:
            v = self._keyring.get(name, f)
            if not self._is_field_optional(f):
                while v is None:  # was not known
                    v = self._ask_and_set(f)
                fields[f] = v
            elif v is not None:
                fields[f] = v
        return fields

    def set(self, **kwargs):
        """Set field(s) of the credential"""
        for f, v in kwargs.items():
            if f not in self._FIELDS:
                raise ValueError("Unknown field %s. Known are: %s"
                                 % (f, self._FIELDS.keys()))
            self._keyring.set(self.name, f, v)

    def get(self, f, default=None):
        """Get a field of the credential"""
        if f not in self._FIELDS:
            raise ValueError("Unknown field %s. Known are: %s"
                             % (f, self._FIELDS.keys()))
        try:
            return self._keyring.get(self.name, f)
        except:  # MIH: what could even happen? _keyring not a dict?
            return default

    def delete(self):
        """Deletes credential values from the keyring"""
        for f in self._FIELDS:
            self._keyring.delete(self.name, f)


class UserPassword(Credential):
    """Simple type of a credential which consists of user/password pair"""

    _FIELDS = OrderedDict([('user', {}),
                           ('password', {'hidden': True})])

    is_expired = False  # no expiration provisioned


class AWS_S3(Credential):
    """Credential for AWS S3 service"""

    _FIELDS = OrderedDict([('key_id', {}),
                           ('secret_id', {'hidden': True}),
                           ('session', {'optional': True}),
                           ('expiration', {'optional': True}),
                           ])

    @property
    def is_expired(self):
        exp = self.get('expiration', None)
        if not exp:
            return True
        exp_epoch = iso8601_to_epoch(exp)
        expire_in = (exp_epoch - calendar.timegm(time.localtime())) / 3600.

        lgr.debug(
            ("Credential %s has expired %.2fh ago"
                if expire_in <= 0 else "Credential %s will expire in %.2fh")
            % (self.name, expire_in))
        return expire_in <= 0


@auto_repr
class CompositeCredential(Credential):
    """Credential which represent a sequence of Credentials where front one is exposed to user
    """

    # To be defined in sub-classes
    _CREDENTIAL_CLASSES = None
    _CREDENTIAL_ADAPTERS = None

    def _prepare(self):
        assert len(self._CREDENTIAL_CLASSES) > 1, "makes sense only if there is > 1 credential"
        assert len(self._CREDENTIAL_CLASSES) == len(self._CREDENTIAL_ADAPTERS) + 1, \
            "there should be 1 less of adapter than _CREDENTIAL_CLASSES"

        for C in self._CREDENTIAL_CLASSES:
            assert issubclass(C, Credential), "%s must be a subclass of Credential" % C

        # First credential should bear the name and url
        credentials = [self._CREDENTIAL_CLASSES[0](self.name, url=self.url, keyring=self._keyring)]
        # and we just reuse its _FIELDS for _ask_field_value etc
        self._FIELDS = credentials[0]._FIELDS
        # the rest with index suffix, but storing themselves in the same keyring
        for iC, C in enumerate(self._CREDENTIAL_CLASSES[1:]):
            credentials.append(
                C(name="%s:%d" % (self.name, iC + 1), url=None, keyring=self._keyring)
            )
        self._credentials = credentials

        super(CompositeCredential, self)._prepare()

    # Here it becomes tricky, since theoretically it is the "tail"
    # ones which might expire etc, so we wouldn't exactly know what
    # new credentials outside process wanted -- it would be silly to ask
    # right away the "entry" credentials if it is just the expiration of the
    # tail credentials
    def enter_new(self):
        # should invalidate/remove all tail credentials to avoid failing attempts to login
        self._credentials[0].enter_new()
        for c in self._credentials[1:]:
            c.delete()

    def __call__(self):
        """Obtain credentials from a keyring and if any is not known -- ask"""
        # Start from the tail until we have credentials set
        idx = len(self._credentials) - 1
        for c in self._credentials[::-1]:
            if c.is_known and not c.is_expired:
                break
            idx -= 1

        if idx < 0:
            # none was known, all the same -- start with the first one
            idx = 0

        # TODO: consider moving logic of traversal into authenticator since it is
        # the one spitting out authentication error etc
        # Theoretically we could just reuse 'fields' from adapter in the next step
        # but let's do full circle, so that if any "normalization" is done by
        # Credentials we take that into account
        for c, adapter, next_c in zip(
                self._credentials[idx:],
                self._CREDENTIAL_ADAPTERS[idx:],
                self._credentials[idx + 1:]):
            fields = c()
            next_fields = adapter(**fields)
            next_c.set(**next_fields)

        return self._credentials[-1]()


def _nda_adapter(user=None, password=None):
    from datalad.support.third.nda_aws_token_generator import NDATokenGenerator
    gen = NDATokenGenerator()
    token = gen.generate_token(user, password)
    # There are also session and expiration we ignore... TODO anything about it?!!!
    # we could create a derived AWS_S3 which would also store session and expiration
    # and then may be Composite could use those????
    return dict(key_id=token.access_key, secret_id=token.secret_key,
                session=token.session, expiration=token.expiration)


class NDA_S3(CompositeCredential):
    """Credential to access NDA AWS

    So for NDA we need a credential which is a composite credential.
    User provides UserPassword and then some adapter generates AWS_S3
    out of it
    """
    _CREDENTIAL_CLASSES = (UserPassword, AWS_S3)
    _CREDENTIAL_ADAPTERS = (_nda_adapter,)


CREDENTIAL_TYPES = {
    'user_password': UserPassword,
    'aws-s3': AWS_S3,
    'nda-s3': NDA_S3,
}
