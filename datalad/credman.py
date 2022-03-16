# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See LICENSE file distributed along with the datalad_osf package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Credential management and query"""

__docformat__ = 'restructuredtext'

__all__ = ['CredentialManager']

from datetime import datetime
import logging
import re

import datalad
from datalad.support.exceptions import (
    CapturedException,
    CommandError,
)
from datalad.ui import ui

lgr = logging.getLogger('datalad.credman')


class CredentialManager(object):
    """Facility to get, set, remove and query credentials.

    A credential in this context is a set of properties (key-value pairs)
    associated with exactly one secret.

    At present, the only backend for secret storage is the Python keyring
    package, as interfaced via a custom DataLad wrapper. Store for credential
    properties is implemented using DataLad's (i.e. Git's) configuration
    system. All properties are stored in the `global` (i.e., user) scope
    under configuration items following the pattern::

      datalad.credential.<name>.<property>

    where ``<name>`` is a credential name/identifier, and ``<property>`` is an
    arbitrarily named credential property, whose name must follow the
    git-config syntax for variable names (case-insensitive, only alphanumeric
    characters and ``-``, and must start with an alphabetic character).

    Create a ``CredentialManager`` instance is fast, virtually no initialization
    needs to be performed. All internal properties are lazily evaluated.
    This facilitate usage of this facility in code where it is difficult
    to incorporate a long-lived central instance.

    API

    With one exception, all parameter names of methods in the main API
    outside ``**kwargs`` must have a ``_`` prefix that distinguishes credential
    properties from method parameters. The one exception is the ``name``
    parameter, which is used as a primary identifier (albeit being optional
    for some operations).
    """
    valid_property_names_regex = re.compile(r'[a-z0-9]+[a-z0-9-]*$')

    def __init__(self, cfg=None):
        """

        Parameters
        ----------
        cfg: ConfigManager, optional
          If given, all configuration queries are performed using this
          ``ConfigManager`` instance. Otherwise ``datalad.cfg`` is used.
        """
        self.__cfg = cfg
        self.__cred_types = None
        self.__keyring = None

    # main API
    #
    def get(self, name=None, _prompt=None, _type_hint=None, **kwargs):
        """Get properties and secret of a credential.

        This is a read-only method that never modifies information stored
        on a credential in any backend.

        Credential property lookup is supported via a number approaches.  When
        providing ``name``, all existing corresponding configuration items are
        found and reported, and an existing secret is retrieved from name-based
        secret backends (presently ``keyring``). When providing a ``type``
        property or a ``_type_hint`` the lookup of additional properties in the
        keyring-backend is enabled, using predefined property name lists
        for a number of known credential types.

        For all given property keys that have no value assigned after the
        initial lookup, manual/interactive entry is attempted, whenever
        a custom ``_prompt`` was provided. This include requesting a secret.
        If manually entered information is contained in the return credential
        record, the record contains an additional ``_edited`` property with a
        value of ``True``.

        If no secret is known after lookup and a potential manual data entry,
        a plain ``None`` is returned instead of a full credential record.

        Parameters
        ----------
        name: str, optional
          Name of the credential to be retrieved
        _prompt: str or None
          Instructions for credential entry to be displayed when missing
          properties are encountered. If ``None``, manual entry is disabled.
        _type_hint: str or None
          In case no ``type`` property is included in ``kwargs``, this parameter
          is used to determine a credential type, to possibly enable further
          lookup/entry of additional properties for a known credential type
        **kwargs:
          Credential property name/value pairs. For any property with a value
          of ``None``, manual data entry will be performed, unless a value
          could be retrieved on lookup, or prompting was not enabled.

        Returns
        -------
        dict or None
          Return ``None``, if no secret for the credential was found or entered.
          Otherwise returns the complete credential record, comprising all
          properties and the secret. An additional ``_edited`` key with a
          value of ``True`` is added whenever the returned record contains
          manually entered information.

        Raises
        ------
        ValueError
          When the method is called without any information that could be
          used to identify a credential
        """
        if name is None and _type_hint is None and not kwargs:
            # there is no chance that this could work
            raise ValueError(
                'CredentialManager.get() called without any identifying '
                'information')
        if name is None:
            # there is no chance we can retrieve any stored properties
            # but we can prompt for some below
            cred = {}
        else:
            # if we have a chance to query for stored legacy credentials
            # we do this first to have the more modern parts of the
            # system overwrite them reliably
            cred = self._get_legacy_field_from_keyring(
                name, kwargs.get('type', _type_hint)) or {}

            var_prefix = _get_cred_cfg_var(name, '')
            # get related info from config
            cred.update({
                k[len(var_prefix):]: v
                for k, v in self._cfg.items()
                if k.startswith(var_prefix)
            })

        # final word on the credential type
        _type_hint = cred.get('type', kwargs.get('type', _type_hint))
        if _type_hint:
            # import the definition of expected fields from the known
            # credential types
            cred_type = self._cred_types.get(
                _type_hint,
                dict(fields=[], secret=None))
            for k in (cred_type['fields'] or []):
                if k == cred_type['secret'] or k in kwargs:
                    # do nothing, if this is the secret key
                    # or if we have an incoming value for this key already
                    continue
                # otherwise make sure we prompt for the essential
                # fields
                kwargs[k] = None

        prompted = False
        for k, v in kwargs.items():
            if k == 'secret':
                # handled below
                continue
            if _prompt and v is None and cred.get(k) is None:
                # ask if enabled, no value was provided,
                # and no value is already on record
                v = self._ask_property(k, None if prompted else _prompt)
                if v is not None:
                    prompted = True
            if v:
                cred[k] = v

        # start locating the secret at the method parameters
        secret = kwargs.get('secret')
        if secret is None and name:
            # get the secret, from the effective config, not just the keystore
            secret = self._get_secret(name, type_hint=_type_hint)
        if _prompt and secret is None:
            secret = self._ask_secret(
                type_hint=self._cred_types.get(
                    _type_hint, {}).get('secret'),
                prompt=None if prompted else _prompt,
            )
            if secret:
                prompted = True

        if not secret:
            # nothing
            return

        cred['secret'] = secret
        if 'type' not in cred and kwargs.get('type'):
            # enhance legacy credentials
            cred['type'] = kwargs.get('type')

        # report whether there were any edits to the credential record
        # (incl. being entirely new), such that consumers can decide
        # to save a credentials, once battle-tested
        if prompted:
            cred['_edited'] = True
        return cred

    def set(self, name, _lastused=False, **kwargs):
        """Set credential properties and secret

        Presently, all supported backends require the specification of
        a credential ``name`` for storage. This may change in the future,
        when support for alternative backends is added, at which point
        the ``name`` parameter would become optional.

        All properties provided as `kwargs` with values that are not ``None``
        will be stored. If ``kwargs`` do not contain a ``secret`` specification,
        manual entry will be attempted. The associated prompt with be either
        the name of the ``secret`` field of a known credential (as identified via
        a ``type`` property), or the label ``'secret'``.

        All properties with an associated value of ``None`` will be removed
        (unset).

        Parameters
        ----------
        name: str
          Credential name
        _lastused: bool, optional
          If set, automatically add an additional credential property
          ``'last-used'`` with the current timestamp in ISO 8601 format.
        **kwargs:
          Any number of credential property key/value pairs. Values of
          ``None`` indicate removal of a property from a credential.

        Returns
        -------
        dict
          key/values of all modified credential properties with respect
          to their previously recorded values.

        Raises
        ------
        RuntimeError
          This exception is raised whenever a property cannot be removed
          successfully. Likely cause is that it is defined in a configuration
          scope or backend for which write-access is not supported.
        ValueError
          When property names in kwargs are not syntax-compliant.
        """
        verify_property_names(kwargs)
        # if we know the type, hence we can do a query for legacy secrets
        # and properties. This will migrate them to the new setup
        # over time
        type_hint = kwargs.get('type')
        cred = self._get_legacy_field_from_keyring(name, type_hint) or {}
        if _lastused:
            cred['last-used'] = datetime.now().isoformat()
        # amend with given properties
        cred.update(**kwargs)

        # remove props
        #
        remove_props = [
            k for k, v in cred.items() if v is None and k != 'secret']
        self._unset_credprops_anyscope(name, remove_props)
        updated = {k: None for k in remove_props}

        # set non-secret props
        #
        set_props = {
            k: v for k, v in cred.items()
            if v is not None and k != 'secret'
        }
        for k, v in set_props.items():
            var = _get_cred_cfg_var(name, k)
            if self._cfg.get(var) == v:
                # desired value already exists, we are not
                # storing again to preserve the scope it
                # was defined in
                continue
            # we always write to the global scope (ie. user config)
            # credentials are typically a personal, not a repository
            # specific entity -- likewise secrets go into a personal
            # not repository-specific store
            # for custom needs users can directly set the respective
            # config
            self._cfg.set(var, v, scope='global', force=True, reload=False)
            updated[k] = v
        if set_props:
            self._cfg.reload()

        # set secret
        #
        # we aim to update the secret in the store, hence we must
        # query for a previous setting in order to reliably report
        # updates
        prev_secret = self._get_secret_from_keyring(name, type_hint)
        if 'secret' not in cred:
            # we have no removal directive, reuse previous secret
            cred['secret'] = prev_secret
        if cred.get('secret') is None:
            # we want to reset the secret, consider active config
            cred['secret'] = \
                self._cfg.get(_get_cred_cfg_var(name, 'secret'))

        if cred.get('secret') is None:
            # we have no secret specified or in the store already: ask
            # typically we would end up here with an explicit attempt
            # to set a credential in a context that is known to an
            # interactive user, hence the messaging here can be simple
            cred['secret'] = self._ask_secret(type_hint=type_hint or 'secret')
        # at this point we will have a secret. it could be from ENV
        # or provided, or entered. we always want to put it in the
        # store
        self._keyring.set(name, 'secret', cred['secret'])
        if cred['secret'] != prev_secret:
            # only report updated if actually different from before
            updated['secret'] = cred['secret']
        return updated

    def remove(self, name, type_hint=None):
        """Remove a credential, including all properties and secret

        Presently, all supported backends require the specification of
        a credential ``name`` for lookup. This may change in the future,
        when support for alternative backends is added, at which point
        the ``name`` parameter would become optional, and additional
        parameters would be added.

        Returns
        -------
        bool
          True if a credential was removed, and False if not (because
          no respective credential was found).

        Raises
        ------
        RuntimeError
          This exception is raised whenever a property cannot be removed
          successfully. Likely cause is that it is defined in a configuration
          scope or backend for which write-access is not supported.
        """
        # prefix for all config variables of this credential
        prefix = _get_cred_cfg_var(name, '')

        def _get_props():
            return (k[len(prefix):] for k in self._cfg.keys()
                    if k.startswith(prefix))

        to_remove = [
            k[len(prefix):] for k in self._cfg.keys()
            if k.startswith(prefix)
        ]
        removed = False
        if to_remove:
            self._unset_credprops_anyscope(name, to_remove)
            removed = True

        # delete the secret from the keystore, if there is any
        def del_field(name, field):
            global removed
            try:
                self._keyring.delete(name, field)
                removed = True
            except Exception as e:
                if self._keyring.get(name, field) is None:
                    # whatever it was, the target is reached
                    CapturedException(e)
                else:
                    # we could not delete the field
                    raise

        del_field(name, 'secret')
        if type_hint:
            # remove legacy records too
            for field in self._cred_types.get(
                    type_hint, {}).get('fields', []):
                del_field(name, field)
        return removed

    def query_(self, **kwargs):
        """Query for all (matching) credentials.

        Credentials are yielded in no particular order.

        This method cannot find credentials for which only a secret
        was deposited in the keyring.

        This method does support lookup of credentials defined in DataLad's
        "provider" configurations.

        Parameters
        ----------
        **kwargs
          If not given, any found credential is yielded. Otherwise,
          any credential must match all property name/value
          pairs

        Yields
        ------
        tuple(str, dict)
          The first element in the tuple is the credential name, the second
          element is the credential record as returned by ``get()`` for any
          matching credential.
        """
        done = set()
        known_credentials = set(
            (k.split('.')[2], None) for k in self._cfg.keys()
            if k.startswith('datalad.credential.')
        )
        from itertools import chain
        for name, type_hint in chain(
                _yield_legacy_credential_names(),
                known_credentials):
            if name in done:
                continue
            done.add(name)
            cred = self.get(name, _prompt=None, _type_hint=type_hint)
            if not cred:
                continue
            if not kwargs:
                yield (name, cred)
            else:
                if all(cred.get(k) == v for k, v in kwargs.items()):
                    yield (name, cred)
                else:
                    continue

    def query(self, _sortby=None, _reverse=True, **kwargs):
        """Query for all (matching) credentials, sorted by a property

        This method is a companion of ``query_()``, and the same limitations
        regarding credential discovery apply.

        In contrast to ``query_()``, this method return a list instead of
        yielding credentials one by one. This returned list is optionally
        sorted.

        Parameters
        ----------
        _sortby: str, optional
          Name of a credential property to provide a value to sort by.
          Credentials that do not carry the specified property always
          sort last, regardless of sort order.
        _reverse: bool, optional
          Flag whether to sort ascending or descending when sorting.
          By default credentials are return in descending property
          value order. This flag does not impact the fact that credentials
          without the property to sort by always sort last.
        **kwargs
          Pass on as-is to ``query_()``

        Returns
        -------
        list(str, dict)
          Each item is a 2-tuple. The first element in each tuple is the
          credential name, the second element is the credential record
          as returned by ``get()`` for any matching credential.
        """
        matches = self.query_(**kwargs)
        if _sortby is None:
            return list(matches)

        # this makes sure that any credential that does not have the
        # sort-by property name sorts to the very end of the list
        # regardless of whether the sorting is ascending or descending
        def get_sort_key(x):
            # x is a tuple as returned by query_()
            prop_indicator = _sortby in x[1]
            if not _reverse:
                prop_indicator = not prop_indicator
            return (prop_indicator, x[1].get(_sortby))

        return sorted(matches, key=get_sort_key, reverse=_reverse)


    # internal helpers
    #
    def _prompt(self, prompt):
        if not prompt:
            return
        ui.message(prompt)

    def _ask_property(self, name, prompt=None):
        if not ui.is_interactive:
            return
        self._prompt(prompt)
        return ui.question(name, title=None)

    def _ask_secret(self, type_hint=None, prompt=None):
        if not ui.is_interactive:
            return
        self._prompt(prompt)
        return ui.question(
            type_hint or 'secret',
            title=None,
            repeat=self._cfg.obtain(
                'datalad.credentials.repeat-secret-entry'),
            hidden=self._cfg.obtain(
                'datalad.credentials.hidden-secret-entry'),
        )

    def _props_defined_in_cfg(self, name, keys):
        return [
            k for k in keys
            if _get_cred_cfg_var(name, k) in self._cfg
        ]

    def _unset_credprops_anyscope(self, name, keys):
        """Reloads the config after unsetting all relevant variables

        This method does not modify the keystore.
        """
        nonremoved_vars = []
        for k in keys:
            var = _get_cred_cfg_var(name, k)
            if var not in self._cfg:
                continue
            try:
                self._cfg.unset(var, scope='global', reload=False)
            except CommandError as e:
                CapturedException(e)
                try:
                    self._cfg.unset(var, scope='local', reload=False)
                except CommandError as e:
                    CapturedException(e)
                    nonremoved_vars.append(var)
        if nonremoved_vars:
            raise RuntimeError(
                f"Cannot remove configuration items {nonremoved_vars} "
                f"for credential, defined outside global or local "
                "configuration scope. Remove manually")
        self._cfg.reload()

    def _get_legacy_field_from_keyring(self, name, type_hint):
        if not type_hint or type_hint not in self._cred_types:
            return

        cred = {}
        lc = self._cred_types[type_hint]
        for field in (lc['fields'] or []):
            if field == lc['secret']:
                continue
            val = self._keyring.get(name, field)
            if val:
                # legacy credentials used property names with underscores,
                # but this is no longer syntax-compliant -- fix on read
                cred[field.replace('_', '-')] = val
        if 'type' not in cred:
            cred['type'] = type_hint
        return cred

    def _get_secret(self, name, type_hint=None):
        secret = self._cfg.get(_get_cred_cfg_var(name, 'secret'))
        if secret is not None:
            return secret
        return self._get_secret_from_keyring(name, type_hint)

    def _get_secret_from_keyring(self, name, type_hint=None):
        """
        Returns
        -------
        str or None
          None is return when no secret for the given credential name
          could be found. Otherwise, the secret is returned.
        """
        # always get the uniform
        secret = self._keyring.get(name, 'secret')
        if secret:
            return secret
        # fall back on a different "field" that is inferred from the
        # credential type
        secret_field = self._cred_types.get(
            type_hint, {}).get('secret')
        if not secret_field:
            return
        secret = self._keyring.get(name, secret_field)
        return secret

    @property
    def _cfg(self):
        """Return a ConfigManager given to __init__() or the global datalad.cfg
        """
        if self.__cfg:
            return self.__cfg
        return datalad.cfg

    @property
    def _keyring(self):
        """Returns the DataLad keyring wrapper

        This internal property may vanish whenever changes to the supported
        backends are made.
        """
        if self.__keyring:
            return self.__keyring
        from datalad.support.keyring_ import keyring
        self.__keyring = keyring
        return keyring

    @property
    def _cred_types(self):
        """Internal property for mapping of credential type names to fields.

        Returns
        -------
        dict
          Legacy credential type name ('token', 'user_password', etc.) as keys,
          and dictionaries as values. Each of these dicts has two keys:
          'fields' (the complete list of "fields" that the credential
          comprises), and 'secret' (the name of the field that represents the
          secret. If there is no secret, the value associated with that key is
          ``None``.
        """
        # at present the credential type specifications are built from the
        # legacy credential types, but this may change at any point in the
        # future
        # here is what that was in Mar 2022
        # 'user_password': {'fields': ['user', 'password'],
        #                   'secret': 'password'},
        # 'token':  {'fields': ['token'], 'secret': 'token'},
        # 'git':    {'fields': ['user', 'password'], 'secret': 'password'}
        # 'aws-s3': {'fields': ['key_id', 'secret_id', 'session', 'expiration'],
        #            'secret': 'secret_id'},
        # 'nda-s3': {'fields': None, 'secret': None},
        # 'loris-token': {'fields': None, 'secret': None},

        if self.__cred_types:
            return self.__cred_types

        from datalad.downloaders import CREDENTIAL_TYPES
        mapping = {}
        for cname, ctype in CREDENTIAL_TYPES.items():
            secret_fields = [
                f for f in (ctype._FIELDS or {})
                if ctype._FIELDS[f].get('hidden')
            ]
            mapping[cname] = dict(
                fields=list(ctype._FIELDS.keys()) if ctype._FIELDS else None,
                secret=secret_fields[0] if secret_fields else None,
            )
        self.__cred_types = mapping
        return mapping

def _yield_legacy_credential_names():
    # query is constrained by non-secrets, no constraints means report all
    # a constraint means *exact* match on all given properties
    from datalad.downloaders.providers import (
        Providers,
        CREDENTIAL_TYPES,
    )
    type_hints = {v: k for k, v in CREDENTIAL_TYPES.items()}

    legacy_credentials = set(
        (p.credential.name, type(p.credential))
        for p in Providers.from_config_files()
        if p.credential
    )
    for name, type_ in legacy_credentials:
        yield (name, type_hints.get(type_))


def verify_property_names(names):
    """Check credential property names for syntax-compliance.

    Parameters
    ----------
    names: iterable

    Raises
    ------
    ValueError
      When any non-compliant property names were found
    """
    invalid_names = [
        k for k in names
        if not CredentialManager.valid_property_names_regex.match(k)
    ]
    if invalid_names:
        raise ValueError(
            f'Unsupported property names {invalid_names}, '
            'must match git-config variable syntax (a-z0-9 and - characters)')


def _get_cred_cfg_var(name, prop):
    """Return a config variable name for a credential property

    Parameters
    ----------
    name : str
      Credential name
    prop : str
      Property name

    Returns
    -------
    str
    """
    return f'datalad.credential.{name}.{prop}'
