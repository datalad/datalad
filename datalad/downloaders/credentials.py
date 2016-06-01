# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Interface information about credentials
"""
from collections import OrderedDict

from ..dochelpers import exc_str
from ..support.keyring_ import keyring
from ..ui import ui
from ..utils import auto_repr

from logging import getLogger
lgr = getLogger('datalad.downloaders.credentials')


@auto_repr
class Credential(object):
    TYPES = {
        'user_password': OrderedDict([('user', {}), ('password', {'hidden': True})]),
        'aws-s3': OrderedDict([('key_id', {}), ('secret_id', {'hidden': True})]),
    }

    def __init__(self, name, type, url):
        self.name = name
        if not type in self.TYPES:
            raise ValueError("I do not know type %s credential. Known: %s"
                             % (type, self.TYPES.keys()))
        self.type = type
        self.url = url

    def _ask_field_value(self, f, hidden=False):
        return ui.question(f,
                           title="You need to authenticate with %r credentials." % self.name +
                                 " %s provides information on how to gain access"
                                 % self.url if self.url else '',
                           hidden=hidden)

    # TODO: I guess it, or subclasses depending on the type
    def enter_new(self):
        # Use ui., request credential fields corresponding to the type
        # TODO: this is duplication with __call__
        fields = self.TYPES[self.type]
        for f, fopts in fields.items():
            v = self._ask_field_value(f, **fopts)
            keyring.set_password(self.uid, f, v)
        pass

    @property
    def uid(self):
        return "datalad-%s" % (self.name,)

    @property
    def is_known(self):
        uid = self.uid
        try:
            return all(keyring.get_password(uid, f) is not None for f in self.TYPES[self.type])
        except Exception as exc:
            lgr.warning("Failed to query keyring: %s" % exc_str(exc))
            return False

    # should implement corresponding handling (get/set) via keyring module
    def __call__(self):
        # TODO: redo not stupid way
        uid = self.uid
        credentials = {}
        for f, fopts in self.TYPES[self.type].items():
            v = keyring.get_password(uid, f)
            while v is None:  # was not known
                v = self._ask_field_value(f, **fopts)
            keyring.set_password(uid, f, v)
            credentials[f] = v

        #values = [keyring.get_password(uid, f) for f in fields]
        #if not all(values):
        # TODO: Fancy form
        return credentials