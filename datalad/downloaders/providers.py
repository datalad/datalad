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


class Authenticator(object):
    """Abstract common class for different types of authentication

    Derived classes should get parameterized with options from the config files
    from "provider:" sections
    """

    # TODO: figure out interface
    pass

def assure_list_from_str(s):
    """Given a multiline string convert it to a list of return None if empty
    """
    if not s:
        return None
    return s.split('\n')

def assure_dict_from_str(s):
    """Given a multiline string with key=value items convert it to a dictionary

    Returns None if input s is empty
    """
    if not s:
        return None
    out = {}
    for value_str in assure_list_from_str(s):
        if not '=' in value_str:
            raise ValueError("{} is not in key=value format".format(repr(value_str)))
        k, v = s.split('=', 1)
        if k in out:
            raise ValueError("key {k} was already defined in {out} but new value {v} was provided".format(k=k, out=out, v=v))
        out[k] = v
    return out

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


@auto_repr
class Provider(object):
    """Abstract class specifying a provider
    """
    def __init__(self, url_re, credential=None, authenticator=None):
        self.url_re = url_re
        self.credential = credential
        self.authenticator = authenticator

@auto_repr
class ProvidersInformation(object):

    def __init__(self):
        """Would load information about related/possible websites requiring authentication from

        - codebase (for now) datalad/downloaders/configs/providers.cfg
        - current handle .datalad/providers/
        - user dir  ~/.config/datalad/providers/
        - system-wide datalad installation/config /etc/datalad/providers/

        For sample configs look into datalad/downloaders/configs/providers.cfg
        """
        # TODO: separate out loading from creation, so we could e.g. add new providers etc
        self._load()

    def _load(self):
        config = SafeConfigParserWithIncludes()
        # TODO: support all those other paths
        config.read([pathjoin(dirname(abspath(__file__)),
                                        'configs',
                                        'providers.cfg')])

        self.providers = {}
        self.credentials = {}
        self._providers_ordered = []  # list with all known url_re's which will be used, with ones matching coming upfront
        for section in config.sections():
            if ':' in section:
                type_, name = section.split(':', 1)
                assert(type_ in {'provider', 'credential'})
                items = getattr(self, type_ + "s")[name] = {
                    o: config.get(section, o) for o in config.options(section)
                }
                items['name'] = name  # duplication of name in the key and entry so we could lpace into _providers_ordered for now
                getattr(self, '_process_' + type_)(items)
            else:
                lgr.warning("Do not know how to treat section %s here" % section)

    def _process_provider(self, items):
        """Process a dictionary specifying the provider and output the Provider instance
        """
        assert ('authentication_type' in items)
        authentication_type = items['authentication_type']
        assert (authentication_type in {'html_form',  'aws-s3', 'xnat', 'none'})  # 'user_password', 's3'
        # we do allow empty one now
        # if authentication_type == 'html_form':
        #    assert 'html_form_url' in items, "Provider {name} lacks 'html_form_url' whenever authentication_type = html_form".format(**items)

        # bringing url_re to "standard" format of a list and populating _providers_ordered
        url_res = items['url_re'] = items['url_re'].split('\n')
        assert url_res, "current implementation relies on having url_re defined"
        self._providers_ordered.append(items)

    def _process_credential(self, items):
        assert ('type' in items)
        authentication_type = items['type']
        assert (authentication_type in {'user_password', 'aws-s3'})  # 'user_password', 's3'


    def get_matching_provider(self, url):
        nproviders = len(self._providers_ordered)
        for i in range(nproviders):
            provider = self._providers_ordered[i]
            for url_re in provider['url_re']:
                if re.match(url_re, url):
                    if i != 0:
                        # place it first
                        # TODO: optimize with smarter datastructures if this becomes a burden
                        del self._providers_ordered[i]
                        self._providers_ordered = [provider] + self._providers_ordered
                        assert(len(self._providers_ordered) == nproviders)
                    return provider

    def __contains__(self, url):
        # go through the known ones, and if found a match -- return True, if not False
        raise NotImplementedError

    def needs_authentication(self, url):
        provider = self.get_matching_provider(url)
        if provider is None:
            return None
        return provider['authentication_type'].lower() != 'none'

    def get_credentials(self, url, new=False):
        """Ask user to enter credentials for a provider matching url
        """
        # find a match among _items
        provider = self.get_matching_provider(url)
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


