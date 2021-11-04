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

from collections import OrderedDict

from ..support.exceptions import (
    AccessDeniedError,
    CapturedException,
)
from ..support.keyring_ import keyring as keyring_
from ..ui import ui
from ..utils import auto_repr
from ..support.network import iso8601_to_epoch

from datalad import cfg as dlcfg
from datalad.config import anything2bool

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
        'repeat',    # UI should repeat entry or not. Set to False to override default logic
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

    @property
    def is_known(self):
        """Return True if values for all fields of the credential are known"""
        try:
            return all(
                self._is_field_optional(f) or self._get_field_value(f) is not None
                for f in self._FIELDS)
        except Exception as exc:
            ce = CapturedException(exc)
            lgr.warning("Failed to query keyring: %s", ce)
            return False

    def _get_field_value(self, field):
        return dlcfg.get('datalad.credential.{name}.{field}'.format(
            name=self.name,
            field=field.replace('_', '-')
        )) or self._keyring.get(self.name, field)

    def _ask_field_value(self, f, instructions=None):
        msg = instructions if instructions else \
            ("You need to authenticate with %r credentials." % self.name +
                  (" %s provides information on how to gain access"
                   % self.url if self.url else ''))

        # provide custom options only if set for the field
        f_props = self._FIELDS[f]
        kwargs = {}
        for p in ('hidden', 'repeat'):
            if p in f_props:
                kwargs[p] = f_props[p]
        return ui.question(
            f,
            title=msg,
            **kwargs
        )

    def _ask_and_set(self, f, instructions=None):
        v = self._ask_field_value(f, instructions=instructions)
        self.set(**{f: v})
        return v

    def enter_new(self, instructions=None, **kwargs):
        """Enter new values for the credential fields

        Parameters
        ----------
        instructions : str, optional
          If given, the auto-generated instructions based on a login-URL are
          replaced by the given string
        **kwargs
          Any given key value pairs with non-None values are used to set the
          field `key` to the given value, without asking for user input
        """
        if kwargs:
            unknown_fields = set(kwargs).difference(self._FIELDS)
            known_fields = set(self._FIELDS).difference(kwargs)
            if unknown_fields:
                raise ValueError(
                    "Unknown to %s field(s): %s.  Known but not specified: %s"
                    % (self,
                       ', '.join(sorted(unknown_fields)),
                       ', '.join(sorted(known_fields))
                       ))
        # Use ui., request credential fields corresponding to the type
        for f in self._FIELDS:
            if kwargs.get(f, None):
                # use given value, don't ask
                self.set(**{f: kwargs[f]})
            elif not self._is_field_optional(f):
                self._ask_and_set(f, instructions=instructions)

    def __call__(self):
        """Obtain credentials from a keyring and if any is not known -- ask"""
        fields = {}
        # check if we shall ask for credentials, even if some are on record
        # already (but maybe they were found to need updating)
        force_reentry = dlcfg.obtain(
            'datalad.credentials.force-ask',
            valtype=anything2bool)
        for f in self._FIELDS:
            # don't query for value if we need to get a new one
            v = None if force_reentry else self._get_field_value(f)
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
            return self._get_field_value(f)
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


class Token(Credential):
    """Simple type of a credential which provides a single token"""

    _FIELDS = OrderedDict([('token', {'hidden': True, 'repeat': False})])

    is_expired = False  # no expiration provisioned


class AWS_S3(Credential):
    """Credential for AWS S3 service"""

    _FIELDS = OrderedDict([('key_id', {'repeat': False}),
                           ('secret_id', {'hidden': True, 'repeat': False}),
                           ('session', {'optional': True}),
                           ('expiration', {'optional': True}),
                           ])

    @property
    def is_expired(self):
        exp = self.get('expiration', None)
        if not exp:
            return False
        exp_epoch = iso8601_to_epoch(exp)
        # -2 to artificially shorten duration of the allotment to avoid
        # possible race conditions between us checking either it has
        # already expired before submitting a request.
        expire_in = (exp_epoch - time.time() - 2) / 3600.

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
        self.refresh()

    def refresh(self):
        """Re-establish "dependent" credentials

        E.g. if code outside was reported that it expired somehow before known expiration datetime
        """
        for c in self._credentials[1:]:
            c.delete()
        # trigger re-establishing the chain
        _ = self()
        if self.is_expired:
            raise RuntimeError("Credential %s expired right upon refresh: should have not happened")

    @property
    def is_expired(self):
        return any(c.is_expired for c in self._credentials)

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
            next_fields = adapter(self, **fields)
            next_c.set(**next_fields)

        return self._credentials[-1]()


def _nda_adapter(composite, user=None, password=None):
    from datalad.support.third.nda_aws_token_generator import NDATokenGenerator
    from .. import cfg
    nda_auth_url = cfg.obtain('datalad.externals.nda.dbserver')
    gen = NDATokenGenerator(nda_auth_url)
    lgr.debug("Generating token for NDA user %s using %s talking to %s",
              user, gen, nda_auth_url)
    try:
        token = gen.generate_token(user, password)
    except Exception as exc:  # it is really just an "Exception"
        exc_str = str(exc).lower()
        # ATM it is "Invalid username and/or password"
        # but who knows what future would bring
        if "invalid" in exc_str and ("user" in exc_str or "password" in exc_str):
            raise AccessDeniedError(exc_str)
        raise
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


def _loris_adapter(composite, user=None, password=None, **kwargs):
    from datalad.support.third.loris_token_generator import LORISTokenGenerator

    gen = LORISTokenGenerator(url=composite.url)
    token = gen.generate_token(user, password)

    return dict(token=token)


class LORIS_Token(CompositeCredential):
    _CREDENTIAL_CLASSES = (UserPassword, Token)
    _CREDENTIAL_ADAPTERS = (_loris_adapter,)

    def __init__(self, name, url=None, keyring=None):
        super(CompositeCredential, self).__init__(name, url, keyring)


CREDENTIAL_TYPES = {
    'user_password': UserPassword,
    'aws-s3': AWS_S3,
    'nda-s3': NDA_S3,
    'token': Token,
    'loris-token': LORIS_Token
}
