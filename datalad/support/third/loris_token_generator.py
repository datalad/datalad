# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### #
import sys
import json

from urllib import parse
from urllib.request import (
    Request,
    urlopen,
)
from urllib.error import HTTPError

from datalad.support.exceptions import (
    AccessDeniedError,
    CapturedException,
)
from datalad.utils import ensure_unicode


class LORISTokenGenerator(object):
    """
    Generate a LORIS API token by making a request to the
    LORIS login API endpoint with the given username
    and password.

    url is the complete URL of the $LORIS/api/$VERSION/login
    endpoint.
    """
    def __init__(self, url=None, method=None, data_how='json', field="token"):
        """

        Parameters
        ----------
        url: str
          API endpoint URL for authentication.
        method: str, optional
          By default we do not specify any, but could be e.g. POST
        field: str, optional
          By default we return 'token' field of the returned value.
          But it could be any other field.
        data_how: 'json', 'urlencode'
        """
        assert(url is not None)
        self.url = url
        self.method = method
        self.field = field
        self.data_how = data_how

    def generate_token(self, user=None, password=None):
        data = {'username': user, 'password' : password}
        encoded_data = {
            'json': json.dumps,
            'urlencode': parse.urlencode
        }[self.data_how](data).encode('utf-8')
        request = Request(self.url, encoded_data, method=self.method)

        try:
            response = urlopen(request)
        except HTTPError as exc:
            raise AccessDeniedError("Could not authenticate into %s: %s"
                                    % (self.url, CapturedException(exc)))

        str_response = ensure_unicode(response.read())
        data = json.loads(str_response)
        return data[self.field]

