# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Metadata parser base class"""


class BaseMetadataParser(object):
    def __init__(self, ds):
        """
        Parameters
        ----------
        ds : dataset instance
          Dataset to extract metadata from.
        """

        self.ds = ds

    def get_dataset_metadata(self):
        """
        Returns
        -------
        dict
          keys are homogenized datalad metadata keys, values are arbitrary
        """
        raise NotImplementedError

    def get_content_metadata(self):
        """Get ALL metadata for all dataset content.

        Returns
        -------
        generator((location, metadata_dict))
        """
        raise NotImplementedError

    def has_metadata(self):
        """Returns whether a dataset provides this kind meta data"""
        raise NotImplementedError

    def get_homogenized_key(self, key):
        # TODO decide on how to error
        return self._key2stdkey.get(key)
