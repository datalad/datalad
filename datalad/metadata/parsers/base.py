# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Metadata parser base class"""

from os.path import exists, join as opj
from datalad.metadata import _get_base_dataset_metadata


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
        return len(self.get_core_metadata_filenames()) > 0

    def get_core_metadata_filenames(self):
        """List of absolute filenames making up the core meta data source"""
        # default implementation, override if _core_metadata_filenames is not
        # used
        dspath = self.ds.path
        fnames = [opj(dspath, f) for f in self._core_metadata_filenames]
        return [f for f in fnames if exists(f)]

    def get_metadata_filenames(self):
        """List of absolute filenames making up the full meta data source"""
        # default implementation: core == full
        return self.get_core_metadata_filenames()

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

    def _get_metadata(self, dsid, basemeta, full):
        raise NotImplementedError
