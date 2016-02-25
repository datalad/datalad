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

import json

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
    """Mimic original dict-based urldb which was dumped to a json file

    but which also had "public_incoming" mapping to map from incoming
    filenames to "public".  Following changes would be done programmatically now
    and we will track only "incoming"

    So internally it is just a dictionary of "fpath: url_info" where url_info is
    a dict containing mtime, size, and url
    """

    __db_version__ = '0.1'

    def __init__(self, data={}):
        self._data = data.copy()
        self._urls = set()  # set of known urls
        self._referenced_files = set()

    def urls(self):
        if not self._urls:
            self._urls = set(x['url'] for x in itervalues(self._data))
        return self._urls

    def __contains__(self, fpath):
        return fpath in self._data

    def get(self, fpath, *args, **kwargs):
        return self._data.get(fpath, *args, **kwargs)

    def __getitem__(self, fpath):
        self._referenced_files.add(fpath)
        return self.get(fpath)

    def __setitem__(self, fpath, v):
        url = v.get('url') # must have URL
        self._urls.add(url)
        self._referenced_files.add(fpath)
        self._data[fpath] = v

    def get_abandoned_files(self):
        """Return files which were not referenced (set or get) in the life-time of this DB
        """
        return set(self._data).difference(self._referenced_files)

    def prune(self, fpaths=None):
        """Prune provided or abandoned (if fpaths is None) files entries
        """
        if fpaths is None:
            fpaths = self.get_abandoned_files()
        for fpath in fpaths:
            if fpath in self._data:
                del self._data[fpath]
        # reset _urls
        self._urls = None
        return self  # for easier chaining

    def save(self, fpath):
        """Save DB as a JSON file
        """
        db = {
            'version': self.__db_version__,
            'data': self._data
        }
        with open(fpath, 'w') as f:
            json.dump(db, f, indent=2, sort_keys=True, separators=(',', ': '))
        return self  # for easier chaining

    def load(self, fpath):
        with open(fpath) as f:
            db = json.load(f)
        if db.get('version') != self.__db_version__:
            raise ValueError("Loaded db from %s is of unsupported version %s. "
                             "Currently supported: %s"
                             % (fpath, db.get('version'), self.__db_version__))
        self.data = db.get('data')
        return self  # for easier chaining

from os.path import lexists
from ..utils import updated
from ..support.network import SimpleURLStamper

# TODO: formatlize above DB into API so we could have various implementations to give to DBNode
class DBNode(object):
    def __init__(self, db, url_stamper=None):
        self.db = db
        if url_stamper is None:
            # TODO: sucks since we would need to inform about mode -- full/fast/relaxed
            url_stamper = SimpleURLStamper()
        self._url_stamper = url_stamper

    def skip_known_url(self, data):
        if data['url'] in self.db.urls:
            return
        yield data

    def skip_existing_file(self, data):
        # Hm... we could have file known AND existing or not.... TODO
        filename = data['filename']   # TODO: filepath probably??
        if filename in self.db and lexists(filename):
            return
        yield data

    def instruct_to_remove_abandoned(self, data):
        # data is not used
        for filename in self.db.get_abandoned_files():
            yield updated(data, {'filename': filename,
                                 'fileaction': 'remove' })

    def check_url(self, data):
        """Check URL for being modified etc"""
        url = data['url']
        filename = data['filename']
        # Get information about that url
        url_stamp = self._url_stamper(url)
        old_url_stamp = self.db.get(filename)
        yield data