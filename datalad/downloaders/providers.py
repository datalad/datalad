# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Information about data providers
"""

import re
from six import iteritems
from six.moves.urllib.parse import urlparse

from os.path import dirname, abspath, join as pathjoin

from ..support.configparserinc import SafeConfigParserWithIncludes
from ..ui import ui

from logging import getLogger
lgr = getLogger('datalad.providers')

def resolve_url_to_name(d, url):
    """Given a directory (e.g. of SiteInformation._items or Credential._items)
    go through url_re and find the corresponding item and returns its key (i.e. name)
    """

    for k, rec in iteritems(d):
        for url_re in rec.get('url_re', '').split('\n'):
            if url_re:
                if re.search(url_re, url):
                    return k
    return None

class ProvidersInformation(object):

    def __init__(self):
        """Would load information about related/possible websites requiring authentication from

        - codebase (for now) datalad/downloaders/configs/providers.cfg
        - current handle .datalad/providers/
        - user dir  ~/.config/datalad/providers/
        - system-wide datalad installation/config /etc/datalad/providers/

        For sample configs look into datalad/downloaders/configs/providers.cfg
        """
        providers_config = SafeConfigParserWithIncludes()
        # TODO: support all those other paths
        providers_config.read([pathjoin(dirname(abspath(__file__)),
                                        'configs',
                                        'providers.cfg')])

        self.providers = {}
        for section in providers_config.sections():
            if section.startswith('provider:'):
                name = section.split(':', 1)[1]
                self.providers[name] = {
                    o: providers_config.get(section, o) for o in providers_config.options(section)
                }
            else:
                lgr.warning("Do not know how to treat section %s here" % section)

    def __contains__(self, url):
        # go through the known ones, and if found a match -- return True, if not False
        raise NotImplementedError

    def get(self, url, field=None):
        # if no field == return all values as a dict
        raise NotImplementedError


# TODO: use keyring module for now
class Credentials(object):
    """The interface to the credentials stored by some backend

        - current handle .datalad/creds/
        - user dir  ~/.config/datalad/creds/
        - system-wide datalad installation/config /etc/datalad/creds/

        Just load all the files, for now in the form of

        [credentials:crcns]
        # url_re = ....         ; optional
        url = https://crcns.org/request-account/   ; url where to request credentials
        type = user_password    ; (user_password|s3_keys(access_key,secret_key for S3)

        where actual fields would be stored in a keyring relying on the OS
        provided secure storage

    """

    def __init__(self):
        self.providers = ProvidersInformation()
        self._items = {}
        self._load()  # populate items with information from the those files

    def _load(self):
        raise NotImplementedError()

    def needs_credentials(self, url):
        return "TODO: url known to self._items" or url in self.providers

    def get_credentials(self, url, new=False):
        # find a match among _items
        name = resolve_url_to_name(self._items, url)
        if new or not name:
            rec = self._get_new_record_ui(url)
            rec['url_re'] = "TODO"  # figure out
            name = urlparse(url).netloc
            self._items[name] = rec
            if ui.yesno("Do you want to store credentials for %s" % name):
                self.store_credentials()
        else:
            return self._items[name]

    def store_credentials(self, name):
        # TODO: store  self._items[name]  in appropriate (user) creds
        # for later reuse
        raise NotImplementedError()

    def _get_new_record_ui(self, url):
        # TODO: should be a dialog with the fields appropriate for this particular
        # type of credentials
        ui.message("To access %s we would need credentials.")
        if url in self.providers:
            self.providers
            ui.message("If you don't yet have credentials, please visit %s"
                       % self.providers.get(url, 'credentials_url'))
        return { 'user': ui.question("Username:"),
                 'password': ui.password() }


# creds = Credentials()
