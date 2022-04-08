# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
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

import re
from os.path import dirname, abspath, join as pathjoin
from urllib.parse import urlparse
from collections import OrderedDict

from .base import NoneAuthenticator, NotImplementedAuthenticator

from .http import (
    HTMLFormAuthenticator,
    HTTPAnonBearerTokenAuthenticator,
    HTTPAuthAuthenticator,
    HTTPBasicAuthAuthenticator,
    HTTPDigestAuthAuthenticator,
    HTTPBearerTokenAuthenticator,
    HTTPDownloader,
)
from .s3 import S3Authenticator, S3Downloader
from .shub import SHubDownloader
from configparser import ConfigParser as SafeConfigParserWithIncludes
from datalad.support.external_versions import external_versions
from datalad.support.network import RI
from datalad.support import path
from datalad.utils import (
    auto_repr,
    ensure_list_from_str,
    get_dataset_root,
    Path,
)

from ..interface.common_cfg import dirs

lgr = getLogger('datalad.downloaders.providers')

# dict to bind authentication_type's to authenticator classes
# parameters will be fetched from config file itself
AUTHENTICATION_TYPES = {
    'html_form': HTMLFormAuthenticator,
    'http_auth': HTTPAuthAuthenticator,
    'http_basic_auth': HTTPBasicAuthAuthenticator,
    'http_digest_auth': HTTPDigestAuthAuthenticator,
    'bearer_token': HTTPBearerTokenAuthenticator,
    'bearer_token_anon': HTTPAnonBearerTokenAuthenticator,
    'aws-s3': S3Authenticator,  # TODO: check if having '-' is kosher
    'nda-s3': S3Authenticator,
    'loris-token': HTTPBearerTokenAuthenticator,
    'xnat': NotImplementedAuthenticator,
    'none': NoneAuthenticator,
}

from datalad.downloaders import CREDENTIAL_TYPES


@auto_repr
class Provider(object):
    """Class to bring together url_res, credential, and authenticator
    """
    # TODO: we might need a lazy loading of the submodules which would provide
    # specific downloaders while importing needed Python modules "on demand"
    DOWNLOADERS = {
        'http': {'class': HTTPDownloader, 'externals': {'requests'}},
        'https': {'class': HTTPDownloader, 'externals': {'requests'}},
        'shub': {'class': SHubDownloader, 'externals': {'requests'}},
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
        self.url_res = ensure_list_from_str(url_res)
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
            # Let's do via kwargs so we could accommodate cases when downloader does not necessarily
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
    _DS_ROOT = None
    _CONFIG_TEMPLATE = """\
# Provider configuration file created to initially access
# {url}

[provider:{name}]
url_re = {url_re}
authentication_type = {authentication_type}
# Note that you might need to specify additional fields specific to the
# authenticator.  Fow now "look into the docs/source" of {authenticator_class}
# {authentication_type}_
credential = {credential_name}

[credential:{credential_name}]
# If known, specify URL or email to how/where to request credentials
# url = ???
type = {credential_type}
"""

    def __init__(self, providers=None):
        """
        """
        self._providers = providers or []
        # a set of providers to handle connections without authentication.
        # Will be setup one per each protocol schema
        self._default_providers = {}

    def __repr__(self):
        return "%s(%s)" % (
            self.__class__.__name__,
            "" if not self._providers else repr(self._providers)
        )

    def __len__(self):
        return len(self._providers)

    def __getitem__(self, index):
        return self._providers[index]

    def __iter__(self):
        return self._providers.__iter__()

    @classmethod
    def _get_providers_dirs(cls, dsroot=None):
        """Return an ordered dict with directories to look for provider config files

        Is implemented as a function to ease mock testing depending on dirs.
        values
        """
        paths = OrderedDict()
        paths['dist'] = pathjoin(dirname(abspath(__file__)), 'configs')
        if dsroot is not None:
            paths['ds'] = pathjoin(dsroot, '.datalad', 'providers')
        paths['site'] = pathjoin(dirs.site_config_dir, "providers") \
            if dirs.site_config_dir else None
        paths['user'] = pathjoin(dirs.user_config_dir, "providers") \
            if dirs.user_config_dir else None
        return paths

    @classmethod
    def _get_configs(cls, dir, files='*.cfg'):
        return glob(pathjoin(dir, files)) if dir is not None else []

    @classmethod
    def from_config_files(cls, files=None, reload=False):
        """Loads information about related/possible websites requiring authentication from:

        - datalad/downloaders/configs/*.cfg files provided by the codebase
        - current dataset .datalad/providers/
        - User's home directory directory (ie ~/.config/datalad/providers/*.cfg)
        - system-wide datalad installation/config (ie /etc/datalad/providers/*.cfg)

        For sample configs files see datalad/downloaders/configs/providers.cfg

        If files is None, loading is cached between calls.  Specify reload=True to force
        reloading of files from the filesystem.  The class method reset_default_providers
        can also be called to reset the cached providers.
        """
        # lazy part
        dsroot = get_dataset_root("")
        if files is None and cls._DEFAULT_PROVIDERS and not reload and dsroot==cls._DS_ROOT:
            return cls._DEFAULT_PROVIDERS

        config = SafeConfigParserWithIncludes()
        files_orig = files
        if files is None:
            cls._DS_ROOT = dsroot
            files = []
            for p in cls._get_providers_dirs(dsroot).values():
                files.extend(cls._get_configs(p))
        config.read(files)

        # We need first to load Providers and credentials
        # Order matters, because we need to ensure that when
        # there's a conflict between configuration files declared
        # at different precedence levels (ie. dataset vs system)
        # the appropriate precedence config wins.
        providers = OrderedDict()
        credentials = {}

        for section in config.sections():
            if ':' in section:
                type_, name = section.split(':', 1)
                assert type_ in {'provider', 'credential'}, "we know only providers and credentials, got type %s" % type_
                items = {
                    o: config.get(section, o) for o in config.options(section)
                }
                # side-effect -- items get popped
                locals().get(type_ + "s")[name] = getattr(
                    cls, '_process_' + type_)(name, items)
                if len(items):
                    raise ValueError("Unprocessed fields left for %s: %s" % (name, str(items)))
            else:
                lgr.warning("Do not know how to treat section %s here" % section)

        # link credentials into providers
        lgr.debug("Assigning credentials into %d providers", len(providers))
        for provider in providers.values():
            if provider.credential:
                if provider.credential not in credentials:
                    raise ValueError("Unknown credential %s. Known are: %s"
                                     % (provider.credential, ", ".join(credentials.keys())))
                provider.credential = credentials[provider.credential]
                # TODO: Is this the right place to pass dataset to credential?
                provider.credential.set_context(dataset=cls._DS_ROOT)

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
        url_res = ensure_list_from_str(items.pop('url_re', []))
        assert url_res, "current implementation relies on having url_re defined"

        credential = items.pop('credential', None)

        # credential instance will be assigned later after all of them are loaded
        return Provider(name=name, url_res=url_res, authenticator=authenticator,
                        credential=credential)

    @classmethod
    def _process_credential(cls, name, items):
        assert 'type' in items, "Credential must specify type.  Missing in %s" % name
        cred_type = items.pop('type')
        if cred_type not in CREDENTIAL_TYPES:
            raise ValueError("I do not know type %s credential. Known: %s"
                             % (cred_type, CREDENTIAL_TYPES.keys()))
        return CREDENTIAL_TYPES[cred_type](name=name, url=items.pop('url', None))

    def reload(self):
        new_providers = self.from_config_files(reload=True)
        self._providers = new_providers._providers
        self._default_providers = new_providers._default_providers

    def get_provider(self, url, only_nondefault=False, return_all=False):
        """Given a URL returns matching provider
        """

        # Range backwards to ensure that more locally defined
        # configuration wins in conflicts between url_re
        matching_providers = []
        for provider in self._providers[::-1]:
            for url_re in provider.url_res:
                try:
                    if re.match(url_re, url):
                        lgr.debug("Returning provider %s for url %s", provider, url)
                        matching_providers.append(provider)
                except re.error:
                    lgr.warning(
                        "Invalid regex %s in provider %s"
                        % (url_re, provider.name)
                    )

        if matching_providers:
            if return_all:
                return matching_providers
            if len(matching_providers) > 1:
                lgr.warning(
                    "Multiple providers matched for %s, using the first one"
                    % url)
            return matching_providers[0]

        if only_nondefault:
            return None

        # None matched -- so we should get a default one per each of used
        # protocols
        scheme = Provider.get_scheme_from_url(url)
        if scheme not in self._default_providers:
            lgr.debug("Initializing default provider for %s", scheme)
            self._default_providers[scheme] = Provider(name="", url_res=["%s://.*" % scheme])
        provider = self._default_providers[scheme]
        lgr.debug("No dedicated provider, returning default one for %s: %s",
                  scheme, provider)
        return provider

    def _store_new(self, url=None, authentication_type=None,
                   authenticator_class=None, url_re=None, name=None,
                   credential_name=None, credential_type=None, level='user'):
        """Stores a provider and credential config and reloads afterwards.

        Note
        ----
        non-interactive version of `enter_new`.
        For now non-public, pending further refactoring

        Parameters
        ----------
        level: str
          Where to store the config. Choices: 'user' (default), 'ds', 'site'

        Returns
        -------
        Provider
          The stored `Provider` as reported by reload
        """

        # We don't ask user for confirmation, so for this non-interactive
        # routine require everything to be explicitly specified.
        if any(not a for a in [url, authentication_type, authenticator_class,
                               url_re, name, credential_name, credential_type]):
            raise ValueError("All arguments must be specified")

        if level not in ['user', 'ds', 'site']:
            raise ValueError("'level' must be one of 'user', 'ds', 'site'")

        providers_dir = Path(self._get_providers_dirs()[level])
        if not providers_dir.exists():
            providers_dir.mkdir(parents=True, exist_ok=True)
        filepath = providers_dir / f"{name}.cfg"
        cfg = self._CONFIG_TEMPLATE.format(**locals())
        filepath.write_bytes(cfg.encode('utf-8'))
        self.reload()
        return self.get_provider(url)

    def enter_new(self, url=None, auth_types=[], url_re=None, name=None,
                  credential_name=None, credential_type=None):
        # TODO: level/location!
        """Create new provider and credential config

        If interactive, this will ask the user to enter the details (or confirm
        default choices). A dedicated config file is written at
        <user_config_dir>/providers/<name>.cfg

        Parameters:
        -----------
        url: str or RI
          URL this config is created for
        auth_types: list
          List of authentication types to choose from. First entry becomes
          default. See datalad.downloaders.providers.AUTHENTICATION_TYPES
        url_re: str
          regular expression; Once created, this config will be used for any
          matching URL; defaults to `url`
        name: str
          name for the provider; needs to be unique per user
        credential_name: str
          name for the credential; defaults to the provider's name
        credential_type: str
          credential type to use (key for datalad.downloaders.CREDENTIAL_TYPES)
        """

        from datalad.ui import ui
        if url and not name:
            ri = RI(url)
            for f in ('hostname', 'name'):
                try:
                    # might need sanitarization
                    name = str(getattr(ri, f))
                except AttributeError:
                    pass
        known_providers_by_name = {p.name: p for p in self._providers}
        providers_user_dir = self._get_providers_dirs()['user']
        while True:
            name = ui.question(
                title="New provider name",
                text="Unique name to identify 'provider' for %s" % url,
                default=name
            )
            filename = pathjoin(providers_user_dir, '%s.cfg' % name)
            if name in known_providers_by_name:
                if ui.yesno(
                    title="Known provider %s" % name,
                    text="Provider with name %s already known. Do you want to "
                         "use it for this session?"
                         % name,
                    default=True
                ):
                    return known_providers_by_name[name]
            elif path.lexists(filename):
                ui.error(
                    "File %s already exists, choose another name" % filename)
            else:
                break

        if not credential_name:
            credential_name = name
        if not url_re:
            url_re = re.escape(url) if url else None
        while True:
            url_re = ui.question(
                title="New provider regular expression",
                text="A (Python) regular expression to specify for which URLs "
                     "this provider should be used",
                default=url_re
            )
            if not re.match(url_re, url):
                ui.error("Provided regular expression doesn't match original "
                         "url.  Please re-enter")
            # TODO: url_re of another provider might match it as well
            #  I am not sure if we have any kind of "priority" setting ATM
            #  to differentiate or to to try multiple types :-/
            else:
                break

        authentication_type = None
        if auth_types:
            auth_types = [
                t for t in auth_types if t in AUTHENTICATION_TYPES
            ]
            if auth_types:
                authentication_type = auth_types[0]

        # Setup credential
        authentication_type = ui.question(
            title="Authentication type",
            text="What authentication type to use",
            default=authentication_type,
            choices=sorted(AUTHENTICATION_TYPES)
        )
        authenticator_class = AUTHENTICATION_TYPES[authentication_type]

        # TODO: need to figure out what fields that authenticator might
        #       need to have setup and ask for them here!

        credential_type = ui.question(
            title="Credential",
            text="What type of credential should be used?",
            choices=sorted(CREDENTIAL_TYPES),
            default=credential_type or getattr(authenticator_class,
                                               'DEFAULT_CREDENTIAL_TYPE')
        )

        cfg = self._CONFIG_TEMPLATE.format(**locals())
        if ui.yesno(
            title="Save provider configuration file",
            text="Following configuration will be written to %s:\n%s"
                % (filename, cfg),
            default='yes'
        ):
            # Just create a configuration file and reload the thing
            return self._store_new(url=url,
                                   authentication_type=authentication_type,
                                   authenticator_class=authenticator_class,
                                   url_re=url_re,
                                   name=name,
                                   credential_name=credential_name,
                                   credential_type=credential_type,
                                   level='user'
                                   )
        else:
            return None


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
