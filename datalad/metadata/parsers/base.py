# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Metadata parser base class"""

from os.path import lexists
from os.path import join as opj
from datalad.metadata import _get_base_dataset_metadata
from datalad.api import get


class BaseMetadataParser(object):
    # subclass can use this to provide a simple list of candidate files
    # to check
    _core_metadata_filenames = []

    def __init__(self, ds):
        """
        Parameters
        ----------
        ds : dataset instance
          Dataset to extract metadata from.
        """

        self.ds = ds

    def has_metadata(self):
        """Returns whether a dataset provides this kind meta data"""
        # default implementation, override with more efficient, if possible
        fnames = [opj(self.ds.path, f) for f in self._core_metadata_filenames]
        return len([f for f in fnames if lexists(f)]) > 0

    def get_core_metadata_files(self):
        """Obtain (if needed) and return list of absolute filenames making up
        the core meta data source"""
        # default implementation, override if _core_metadata_filenames is not
        # used
        dspath = self.ds.path
        for r in self.ds.get(self._core_metadata_filenames):
            if r['status'] in ('ok', 'notneeded'):
                yield r['path']

    def get_metadata_files(self):
        """Obtain (if needed) and return list of absolute filenames making up
        the full meta data source"""
        # default implementation: core == full
        return self.get_core_metadata_files()

    def get_metadata(self, dsid=None, full=False):
        """Returns JSON-LD compliant meta data structure

        Parameter
        ---------
        full : bool
          If True, all intelligible meta data is return. Otherwise only
          meta data deemed essential by the author is returned.

        Returns
        -------
        dict
          JSON-LD compliant
        """
        if dsid is None:
            dsid = self.ds.id
        meta = _get_base_dataset_metadata(dsid)
        if self.has_metadata():
            meta = self._get_metadata(dsid, meta, full)
        return meta

    def get_global_metadata(self):
        """Returns dataset global metadata

        Returns
        -------
        dict
          Keys should be a subset of the those commoly defined
          by DataLad
        """
        # XXX for now this is reusing the old methods
        meta = self._get_metadata(None, {}, False)
        return meta if meta else None

    def _get_metadata(self, dsid, basemeta, full):
        raise NotImplementedError

    def get_homogenized_key(self, key):
        # TODO decide on how to error
        return self._key2stdkey.get(key)
