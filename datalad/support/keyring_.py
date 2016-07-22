# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Adapters and decorators for keyrings
"""


class Keyring(object):
    """Adapter to keyring module

    It also delays import of keyring which takes 300ms I guess due to all plugins etc
    """
    def __init__(self):
        self.__keyring = None

    @property
    def _keyring(self):
        if self.__keyring is None:
            # Setup logging for keyring if we are debugging, althought keyring's logging
            # is quite scarce ATM
            from .. import lgr
            import logging
            lgr_level = lgr.getEffectiveLevel()
            if lgr_level < logging.DEBUG:
                keyring_lgr = logging.getLogger('keyring')
                keyring_lgr.setLevel(lgr_level)
                keyring_lgr.handlers = lgr.handlers
            lgr.debug("Importing keyring")
            import keyring
            self.__keyring = keyring

        return self.__keyring

    @classmethod
    def _get_service_name(cls, name):
        return "datalad-%s" % str(name)

    # proxy few methods of interest explicitly, to be rebound to the module's
    def get(self, name, field):
        return self._keyring.get_password(self._get_service_name(name), field)

    def set(self, name, field, value):
        return self._keyring.set_password(self._get_service_name(name), field, value)

    def delete(self, name, field=None):
        if field is None:
            raise NotImplementedError("Deletion of all fields associated with a name")
        return self._keyring.delete_password(self._get_service_name(name), field)


class MemoryKeyring(object):
    """A simple keyring which just stores provided info in memory

    Primarily for testing
    """

    def __init__(self):
        self.entries = {}

    def get(self, name, field):
        """Get password from the specified service.
        """
        key = (name, field)
        # to mimic behavior of keyring module
        return self.entries[key] if key in self.entries else None


    def set(self, name, field, value):
        """Set password for the user in the specified service.
        """
        self.entries[(name, field)] = value

    def delete(self, name, field=None):
        """Delete password from the specified service.
        """
        if field:
            self.entries.pop((name, field))
        else:
            deleted = False
            # TODO: might be implemented by some super class if .keys() of some kind provided
            for name_, field_ in self.entries.copy():
                if name == name_:
                    deleted = True
                    self.delete(name_, field_)
            if not deleted:
                raise KeyError("No entries associated with %s" % name)


keyring = Keyring()