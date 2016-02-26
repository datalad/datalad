# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Helper to delay import of keyring which takes 300ms I guess due to all plugins etc

"""

class _Keyring(object):
    def __init__(self):
        self.__keyring = None

    @property
    def _keyring(self):
        if self.__keyring is None:
            import keyring
            self.__keyring = keyring
        return self.__keyring

    # proxy few methods of interest explicitly, to be rebound to the module's
    def get_password(self, *args, **kwargs):
        return self._keyring.get_password(*args, **kwargs)

    def set_password(self, *args, **kwargs):
        return self._keyring.set_password(*args, **kwargs)

keyring = _Keyring()
#import keyring