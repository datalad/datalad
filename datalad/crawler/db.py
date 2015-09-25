# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Module to provide DB for storing crawling/available information"""

from abc import ABCMeta, abstractmethod, abstractproperty
from six import itervalues

class URLDB(object):
    """Database collating urls for the content across all handles

    Schema: TODO, but needs for sure

    - URL (only "public" or internal as for content from archives, or that separate table?)
    - common checksums which we might use/rely upon (MD5, SHA1, SHA256, SHA512)
    - last_checked (if online)
    - last_verified (when verified to contain the content according to the checksums

    allow to query by any known checksum
    """

    __metaclass__ = ABCMeta

    @abstractmethod
    def __contains__(self, url):
        """Return True if DB knows about this URL """
        pass

    @abstractmethod
    def __getitem__(self, url):
        """Given url, return file names where it was downloaded"""
        pass

class JsonURLDB(URLDB):
    """Mimicues original dict-based urldb which was dumped to a json file

    but which also had "public_incoming" mapping to map from incoming
    filenames to "public".  Following changes would be done programatically now
    and we will track only "incoming"

    So internally it is just a dictionary of "file: url_info" where url_info is
    a dict containing mtime, size, and url
    """
    def __init__(self):
        self._data = {}

    def __contains__(self, url):
        return any(x['url'] == url for x in itervalues(self._data))

    def __contains__(self, url):
        return any(x['url'] == url for x in itervalues(self._data))

