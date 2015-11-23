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
from ..utils import auto_repr

from logging import getLogger
lgr = getLogger('datalad.downloaders.providers')

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


def assure_list_from_str(s):
    """Given a multiline string convert it to a list of return None if empty

    Parameters
    ----------
    s: str or list
    """

    if not s:
        return None

    if isinstance(s, list):
        return s
    return s.split('\n')


def assure_dict_from_str(s):
    """Given a multiline string with key=value items convert it to a dictionary

    Parameters
    ----------
    s: str or dict

    Returns None if input s is empty
    """

    if not s:
        return None

    if isinstance(s, dict):
        return s

    out = {}
    for value_str in assure_list_from_str(s):
        if '=' not in value_str:
            raise ValueError("{} is not in key=value format".format(repr(value_str)))
        k, v = value_str.split('=', 1)
        if k in out:
            err  = "key {} was already defined in {}, but new value {} was provided".format(k, out, v)
            raise ValueError(err)
        out[k] = v
    return out


class Authenticator(object):
    """Abstract common class for different types of authentication

    Derived classes should get parameterized with options from the config files
    from "provider:" sections
    """

    # TODO: figure out interface
    pass


class NotImplementedAuthenticator(Authenticator):
    def __init__(self, *args, **kwargs):
        lgr.warning("Necessary authenticator is not yet implemented") # raise NotImplementedError()

@auto_repr
class HTMLFormAuthenticator(Authenticator):
    def __init__(self, fields, url=None, tagid=None, failure_re=None, success_re=None, **kwargs):
        """

        Example specification in the .ini config file
        [provider:crcns]
        ...
        credential = crcns ; is not given to authenticator as is
        authentication_type = html_form
        html_form_url = https://crcns.org/login_form
        html_form_tagid = login_form
        html_form_fields = __ac_name={user}
                   __ac_password={password}
                   submit=Log in
                   form.submitted=1
                   js_enabled=0
                   cookies_enabled=
        html_form_failure_re = (Login failed|Please log in)
        html_form_success_re = You are now logged in

        Parameters
        ----------
        fields : str or dict
          String or a dictionary, which will be used (along with credential) information
          to feed into the form
        url : str, optional
          URL where to find the form to authenticate.  If not provided, an original query url
          which will be provided to the __call__ of the authenticator will be used, so on that
          request it must provide the HTML form. If not -- error will be raised
        tagid : str, optional
          id of the HTML <form> in the document to use. If None, and page contains a single form,
          that one will be used.  If multiple forms -- error will be raise
        failure_re : str or list of str, optional
        success_re : str or list of str, optional
          Regular expressions to determine either login has failed or succeeded.
          TODO: we might condition when it gets ran
        """

        super(HTMLFormAuthenticator, self).__init__(**kwargs)
        self.fields = assure_dict_from_str(fields)
        self.url = url
        self.tagid = tagid
        self.failure_re = assure_list_from_str(failure_re)
        self.success_re = assure_list_from_str(success_re)

    def authenticate(self, url, credential):
        # we should use specified URL for this authentication first
        form_url = self.url if self.url else url

        pass

from .http import HTTPDownloader

@auto_repr
class Provider(object):
    """Class to bring together url_res, credential, and authenticator
    """
    # TODO: we might need a lazy loading of the submodules which would provide
    # specific downloaders while importing needed Python modules "on demand"
    DOWNLOADERS = {'http': HTTPDownloader,
                   'https': HTTPDownloader,
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
        url_split = urlparse(url)
        return url_split.scheme  # , url_split.netloc)

    @classmethod
    def _get_downloader_class(cls, url):
        #if key in self._downloaders:
        key = cls.get_sceme_from_url(url)
        if key in cls.DOWNLOADERS:
            return cls.DOWNLOADERS[key]
        else:
            raise ValueError("Do not know how to handle url %s for scheme %s. Known: %s"
                             % (url, key, cls.DOWNLOADERS.keys()))

    def get_downloader(self, url):
        """Assigns proper downloader given the URL

        If one is known -- verifies its appropriateness for the given url.
        ATM we do not support multiple types of downloaders per single provider
        """
        if self._downloader is None:
            # we need to create a new one
            Downloader = self._get_downloader_class(url)
            # we need to provide it with credentials and authenticator
            self._downloader = Downloader(credential=self.credential, authenticator=self.authenticator)
        return self._downloader


@auto_repr
class Credential(object):
    def __init__(self, name, type, url):
        self.name = name
        self.type = type
        self.url = url


class Providers(object):
    """

    So we could provide handling for URLs with corresponding credentials
    and specific (reusable) downloader.  Internally it contains
    Providers and interfaces them based on a given URL.  Each provider
    in turn takes care about associated with it Downloader.
    """

    # dict to bind authentication_type's to authenticator classes
    # parameters will be fetched from config file itself
    AUTHENTICATION_TYPES = {
        'html_form': HTMLFormAuthenticator,
        'aws-s3': NotImplementedAuthenticator,  # TODO: check if having '-' is kosher
        'xnat': NotImplementedAuthenticator,
        'none': None,
    }

    CREDENTIAL_TYPES = {
        'user_password',
        'aws-s3'
    }

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
    def from_config_files(cls, files=None):
        """Would load information about related/possible websites requiring authentication from

        - codebase (for now) datalad/downloaders/configs/providers.cfg
        - current handle .datalad/providers/
        - user dir  ~/.config/datalad/providers/
        - system-wide datalad installation/config /etc/datalad/providers/

        For sample configs look into datalad/downloaders/configs/providers.cfg
        """
        config = SafeConfigParserWithIncludes()
        # TODO: support all those other paths
        if files is None:
            files = [pathjoin(dirname(abspath(__file__)), 'configs', 'providers.cfg')]
        config.read(files)

        # We need first to load Providers and credentials
        providers = {}
        credentials = {}

        for section in config.sections():
            if ':' in section:
                type_, name = section.split(':', 1)
                assert(type_ in {'provider', 'credential'})
                items = {
                    o: config.get(section, o) for o in config.options(section)
                }
                # side-effect -- items get poped
                locals().get(type_+"s")[name] = getattr(cls, '_process_' + type_)(name, items)
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

        return Providers(providers.values())


    @classmethod
    def _process_provider(cls, name, items):
        """Process a dictionary specifying the provider and output the Provider instance
        """
        assert 'authentication_type' in items, "Must have authentication_type specified"

        auth_type = items.pop('authentication_type')
        if auth_type not in cls.AUTHENTICATION_TYPES:
            raise ValueError("Unknown authentication_type=%s. Known are: %s"
                             % (auth_type, ', '.join(cls.AUTHENTICATION_TYPES)))

        if auth_type != 'none':
            authenticator = cls.AUTHENTICATION_TYPES[auth_type](
                # Extract all the fields as keyword arguments
                **{k[len(auth_type)+1:]: items.pop(k)
                   for k in items.keys()
                   if k.startswith(auth_type+"_")}
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
        return Credential(name=name, type=cred_type, url=items.pop('url', None))


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
                    return provider

        if only_nondefault:
            return None

        # None matched -- so we should get a default one per each of used
        # protocols
        scheme = Provider.get_scheme_from_url(url)
        if scheme not in self._default_providers:
            lgr.debug("Initializing default provider for %s" % scheme)
            self._default_providers[scheme] = Provider(name="", url_res=["%s://.*" % scheme])
        lgr.debug("No dedicated provider, returning default one for %s" % scheme)
        return self._default_providers[scheme]


    #def __contains__(self, url):
    #    # go through the known ones, and if found a match -- return True, if not False
    #    raise NotImplementedError

    def needs_authentication(self, url):
        provider = self.get_provider(url, only_nondefault=True)
        if provider is None:
            return None
        return provider.authenticator is not None

    def get_credentials(self, url, new=False):
        """Ask user to enter credentials for a provider matching url
        """
        # find a match among _items
        provider = self.get_provider(url)
        if new or not provider:
            rec = self._get_new_record_ui(url)
            rec['url_re'] = "TODO"  # present to user and ask to edit
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
        ui.message("To access %s we would need credentials." % url)
        if url in self.providers:
            ui.message("If you don't yet have credentials, please visit %s"
                       % self.providers.get(url, 'credentials_url'))
        return { 'user': ui.question("Username:"),
                 'password': ui.password() }


