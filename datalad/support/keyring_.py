# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Adapters and decorators for keyrings
"""

import os
import logging
lgr = logging.getLogger('datalad.support.keyring')


class Keyring(object):
    """Adapter to keyring module

    It also delays import of keyring which takes 300ms I guess due to all plugins etc
    """
    def __init__(self, keyring_backend=None):
        """

        Parameters
        ----------
        keyring_backend: keyring.backend.KeyringBackend, optional
          Specific keyring to use.  If not provided, the one returned by
          `keyring.get_keyring()` is used
        """
        self.__keyring = keyring_backend
        self.__keyring_mod = None

    @property
    def _keyring(self):
        if self.__keyring_mod is None:
            # Setup logging for keyring if we are debugging, although keyring's logging
            # is quite scarce ATM
            from datalad.log import lgr
            import logging
            lgr_level = lgr.getEffectiveLevel()
            if lgr_level < logging.DEBUG:
                keyring_lgr = logging.getLogger('keyring')
                keyring_lgr.setLevel(lgr_level)
                keyring_lgr.handlers = lgr.handlers
            lgr.debug("Importing keyring")
            import keyring
            self.__keyring_mod = keyring

        if self.__keyring is None:
            from datalad.log import lgr
            # we use module bound interfaces whenever we were not provided a dedicated
            # backend
            self.__keyring = self.__keyring_mod
            the_keyring = self.__keyring_mod.get_keyring()
            if the_keyring.name.lower().startswith('null '):
                lgr.warning(
                    "Keyring module returned '%s', no credentials will be provided",
                    the_keyring.name
                )
        return self.__keyring

    @classmethod
    def _get_service_name(cls, name):
        return "datalad-%s" % str(name)

    # proxy few methods of interest explicitly, to be rebound to the module's
    def get(self, name, field):
        # consult environment, might be provided there and should take precedence
        # NOTE: This env var specification is outdated and not advertised
        # anymmore, but needs to be supported. For example, it is used with and
        # was advertised for
        # https://github.com/datalad-datasets/human-connectome-project-openaccess
        env_var = ('DATALAD_%s_%s' % (name, field)).replace('-', '_')
        lgr.log(5, 'Credentials lookup attempt via env var %s', env_var)
        if env_var in os.environ:
            return os.environ[env_var]
        return self._keyring.get_password(self._get_service_name(name), field)

    def set(self, name, field, value):
        return self._keyring.set_password(self._get_service_name(name), field, value)

    def delete(self, name, field=None):
        if field is None:
            raise NotImplementedError("Deletion of all fields associated with a name")
        try:
            return self._keyring.delete_password(self._get_service_name(name), field)
        except self.__keyring_mod.errors.PasswordDeleteError as exc:
            exc_str = str(exc).lower()
            if 'not found' in exc_str or 'no such password' in exc_str:
                return
            raise


class MemoryKeyring(object):
    """A simple keyring which just stores provided info in memory

    Primarily for testing
    """

    def __init__(self):
        self.entries = {}

    def get(self, name, field):
        """Get password from the specified service.
        """
        # to mimic behavior of keyring module
        return self.entries[name][field] \
            if name in self.entries and field in self.entries[name] \
            else None

    def set(self, name, field, value):
        """Set password for the user in the specified service.
        """
        self.entries.setdefault(name, {}).update({field: value})

    def delete(self, name, field=None):
        """Delete password from the specified service.
        """
        if name in self.entries:
            if field:
                self.entries[name].pop(field)
            else:
                # TODO: might be implemented by some super class if .keys() of some kind provided
                self.entries.pop(name)
        else:
            raise KeyError("No entries associated with %s" % name)


keyring = Keyring()
