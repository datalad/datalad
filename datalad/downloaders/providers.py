# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Data providers - bind downloaders and credentials together
"""

from glob import glob
from logging import getLogger
from six import iteritems

import re
from os.path import dirname, abspath, join as pathjoin
from six.moves.urllib.parse import urlparse

from .base import NoneAuthenticator, NotImplementedAuthenticator

from .http import HTMLFormAuthenticator, HTTPBasicAuthAuthenticator, HTTPDigestAuthAuthenticator
from .http import HTTPDownloader
from .s3 import S3Authenticator, S3Downloader
from ..support.configparserinc import SafeConfigParserWithIncludes
from ..support.external_versions import external_versions
from ..utils import assure_list_from_str
from ..utils import auto_repr

lgr = getLogger('datalad.downloaders.providers')

# dict to bind authentication_type's to authenticator classes
# parameters will be fetched from config file itself
AUTHENTICATION_TYPES = {
    'html_form': HTMLFormAuthenticator,
    'http_auth': HTTPBasicAuthAuthenticator,
    'http_basic_auth': HTTPBasicAuthAuthenticator,
    'http_digest_auth': HTTPDigestAuthAuthenticator,
    'aws-s3': S3Authenticator,  # TODO: check if having '-' is kosher
    'nda-s3': S3Authenticator,
    'xnat': NotImplementedAuthenticator,
    'none': NoneAuthenticator,
}

from .credentials import CREDENTIAL_TYPES


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


@auto_repr
class Provider(object):
    """Class to bring together url_res, credential, and authenticator
    """
    # TODO: we might need a lazy loading of the submodules which would provide
    # specific downloaders while importing needed Python modules "on demand"
    DOWNLOADERS = {
        'http': {'class': HTTPDownloader, 'externals': {'requests'}},
        'https': {'class': HTTPDownloader, 'externals': {'requests'}},
        'ftp': {'class': HTTPDownloader, 'externals': {'requests', 'boto'}},
        's3': {'class': S3Downloader, 'externals': {'boto'}}
        # ... TODO
    }

    def __init__(self, name, url_res, credential=None, authenticator=None,
                 downloader=None):
        """
        Parameters
        ----------
        name: str
        url_res: list of str
           Regular expressions
        credential: Credential, optional
        authenticator: Authenticator, optional
        downloader: Downloader, optional

        """
        self.name = name
        self.url_res = assure_list_from_str(url_res)
        self.credential = credential
        self.authenticator = authenticator
        self._downloader = downloader

    @property
    def downloader(self):
        return self._downloader

    @staticmethod
    def get_scheme_from_url(url):
        """Given a URL return scheme to decide which downloader class to use
        """
        url_split = urlparse(url)
        return url_split.scheme  # , url_split.netloc)

    @classmethod
    def _get_downloader_class(cls, url):
        key = cls.get_scheme_from_url(url)
        if key in cls.DOWNLOADERS:
            entry = cls.DOWNLOADERS[key]
            klass = entry['class']
            for ext in entry.get('externals', set()):
                if external_versions[ext] is None:
                    raise RuntimeError(
                        "For using %s downloader, you need '%s' dependency "
                        "which seems to be missing" % (klass, ext)
                    )
            return klass
        else:
            raise ValueError("Do not know how to handle url %s for scheme %s. Known: %s"
                             % (url, key, cls.DOWNLOADERS.keys()))

    def get_downloader(self, url, **kwargs):
        """Assigns proper downloader given the URL

        If one is known -- verifies its appropriateness for the given url.
        ATM we do not support multiple types of downloaders per single provider
        """
        if self._downloader is None:
            # we need to create a new one
            Downloader = self._get_downloader_class(url)
            # we might need to provide it with credentials and authenticator
            # Let's do via kwargs so we could accomodate cases when downloader does not necessarily
            # cares about those... duck typing or what it is in action
            kwargs = kwargs.copy()
            if self.credential:
                kwargs['credential'] = self.credential
            if self.authenticator:
                kwargs['authenticator'] = self.authenticator
            self._downloader = Downloader(**kwargs)
        return self._downloader


class Providers(object):
    """

    So we could provide handling for URLs with corresponding credentials
    and specific (reusable) downloader.  Internally it contains
    Providers and interfaces them based on a given URL.  Each provider
    in turn takes care about associated with it Downloader.
    """

    _DEFAULT_PROVIDERS = None

    def __init__(self, providers=None):
        """
        """
        self._providers = providers or []
        # a set of providers to handle connections without authentication.
        # Will be setup one per each protocol schema
        self._default_providers = {}

    def __repr__(self):
        return "%s(%s)" % (self.__class__.__name__, "" if not self._providers else repr(self._providers))

    def __len__(self):
        return len(self._providers)

    def __getitem__(self, index):
        return self._providers[index]

    def __iter__(self):
        return self._providers.__iter__()

    @classmethod
    def from_config_files(cls, files=None, reload=False):
        """Would load information about related/possible websites requiring authentication from

        - codebase (for now) datalad/downloaders/configs/providers.cfg
        - current dataset .datalad/providers/
        - user dir  ~/.config/datalad/providers/
        - system-wide datalad installation/config /etc/datalad/providers/

        For sample configs look into datalad/downloaders/configs/providers.cfg

        If files is None, loading is "lazy".  Specify reload=True to force
        reload.  reset_default_providers could also be used to reset the memoized
        providers
        """
        # lazy part
        if files is None and cls._DEFAULT_PROVIDERS and not reload:
            return cls._DEFAULT_PROVIDERS

        config = SafeConfigParserWithIncludes()
        # TODO: support all those other paths
        files_orig = files
        if files is None:
            files = glob(pathjoin(dirname(abspath(__file__)), 'configs', '*.cfg'))
        config.read(files)

        # We need first to load Providers and credentials
        providers = {}
        credentials = {}

        for section in config.sections():
            if ':' in section:
                type_, name = section.split(':', 1)
                assert type_ in {'provider', 'credential'}, "we know only providers and credentials, got type %s" % type_
                items = {
                    o: config.get(section, o) for o in config.options(section)
                }
                # side-effect -- items get poped
                locals().get(type_ + "s")[name] = getattr(
                    cls, '_process_' + type_)(name, items)
                if len(items):
                    raise ValueError("Unprocessed fields left for %s: %s" % (name, str(items)))
            else:
                lgr.warning("Do not know how to treat section %s here" % section)

        # link credentials into providers
        lgr.debug("Assigning credentials into %d providers" % len(providers))
        for provider in providers.values():
            if provider.credential:
                if provider.credential not in credentials:
                    raise ValueError("Unknown credential %s. Known are: %s"
                                     % (provider.credential, ", ".join(credentials.keys())))
                provider.credential = credentials[provider.credential]

        providers = Providers(list(providers.values()))

        if files_orig is None:
            # Store providers for lazy access
            cls._DEFAULT_PROVIDERS = providers

        return providers

    @classmethod
    def reset_default_providers(cls):
        """Resets to None memoized by from_config_files providers
        """
        cls._DEFAULT_PROVIDERS = None

    @classmethod
    def _process_provider(cls, name, items):
        """Process a dictionary specifying the provider and output the Provider instance
        """
        assert 'authentication_type' in items, "Must have authentication_type specified"

        auth_type = items.pop('authentication_type')
        if auth_type not in AUTHENTICATION_TYPES:
            raise ValueError("Unknown authentication_type=%s. Known are: %s"
                             % (auth_type, ', '.join(AUTHENTICATION_TYPES)))

        if auth_type != 'none':
            authenticator = AUTHENTICATION_TYPES[auth_type](
                # Extract all the fields as keyword arguments
                **{k[len(auth_type) + 1:]: items.pop(k)
                   for k in list(items.keys())
                   if k.startswith(auth_type + "_")}
            )
        else:
            authenticator = None

        # bringing url_re to "standard" format of a list and populating _providers_ordered
        url_res = assure_list_from_str(items.pop('url_re'))
        assert url_res, "current implementation relies on having url_re defined"

        credential = items.pop('credential', None)

        # credential instance will be assigned later after all of them are loaded
        return Provider(name=name, url_res=url_res, authenticator=authenticator,
                        credential=credential)

    @classmethod
    def _process_credential(cls, name, items):
        assert 'type' in items, "Credential must specify type.  Missing in %s" % name
        cred_type = items.pop('type')
        if not cred_type in CREDENTIAL_TYPES:
            raise ValueError("I do not know type %s credential. Known: %s"
                             % (cred_type, CREDENTIAL_TYPES.keys()))
        return CREDENTIAL_TYPES[cred_type](name=name, url=items.pop('url', None))

    def get_provider(self, url, only_nondefault=False):
        """Given a URL returns matching provider
        """
        nproviders = len(self._providers)
        for i in range(nproviders):
            provider = self._providers[i]
            if not provider.url_res:
                continue
            for url_re in provider.url_res:
                if re.match(url_re, url):
                    if i != 0:
                        # place it first
                        # TODO: optimize with smarter datastructures if this becomes a burden
                        del self._providers[i]
                        self._providers = [provider] + self._providers
                        assert(len(self._providers) == nproviders)
                    lgr.debug("Returning provider %s for url %s", provider, url)
                    return provider

        if only_nondefault:
            return None

        # None matched -- so we should get a default one per each of used
        # protocols
        scheme = Provider.get_scheme_from_url(url)
        if scheme not in self._default_providers:
            lgr.debug("Initializing default provider for %s" % scheme)
            self._default_providers[scheme] = Provider(name="", url_res=["%s://.*" % scheme])
        provider = self._default_providers[scheme]
        lgr.debug("No dedicated provider, returning default one for %s: %s",
                  scheme, provider)
        return provider

    # TODO: avoid duplication somehow ;)
    # Sugarings to get easier access to downloaders
    def download(self, url, *args, **kwargs):
        return self.get_provider(url).get_downloader(url).download(url, *args, **kwargs)

    def fetch(self, url, *args, **kwargs):
        return self.get_provider(url).get_downloader(url).fetch(url, *args, **kwargs)

    def get_status(self, url, *args, **kwargs):
        return self.get_provider(url).get_downloader(url).get_status(url, *args, **kwargs)

    def needs_authentication(self, url):
        provider = self.get_provider(url, only_nondefault=True)
        if provider is None:
            return None
        return provider.authenticator is not None


    # # TODO: UNUSED?
    # def get_credentials(self, url, new=False):
    #     """Ask user to enter credentials for a provider matching url
    #     """
    #     # find a match among _items
    #     provider = self.get_provider(url)
    #     if new or not provider:
    #         rec = self._get_new_record_ui(url)
    #         rec['url_re'] = "TODO"  # present to user and ask to edit
    #         name = urlparse(url).netloc
    #         self._items[name] = rec
    #         if ui.yesno("Do you want to store credentials for %s" % name):
    #             self.store_credentials()
    #     else:
    #         return self._items[name]
    #
    # def store_credentials(self, name):
    #     # TODO: store  self._items[name]  in appropriate (user) creds
    #     # for later reuse
    #     raise NotImplementedError()
    #
    # def _get_new_record_ui(self, url):
    #     # TODO: should be a dialog with the fields appropriate for this particular
    #     # type of credentials
    #     ui.message("To access %s we would need credentials." % url)
    #     if url in self.providers:
    #         ui.message("If you don't yet have credentials, please visit %s"
    #                    % self.providers.get(url, 'credentials_url'))
    #     return { 'user': ui.question("Username:"),
    #              'password': ui.password() }
