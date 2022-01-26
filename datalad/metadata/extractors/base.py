# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Metadata extractor base class"""


class BaseMetadataExtractor(object):

    NEEDS_CONTENT = True   # majority of the extractors need data content

    def __init__(self, ds, paths):
        """
        Parameters
        ----------
        ds : dataset instance
          Dataset to extract metadata from.
        paths : list
          Paths to investigate when extracting content metadata
        """

        self.ds = ds
        self.paths = paths

    def get_metadata(self, dataset=True, content=True):
        """
        Returns
        -------
        dict or None, dict or None
          Dataset metadata dict, dictionary of filepath regexes with metadata,
          dicts, each return value could be None if there is no such metadata
        """
        # default implementation
        return \
            self._get_dataset_metadata() if dataset else None, \
            ((k, v) for k, v in self._get_content_metadata()) if content else None

    def _get_dataset_metadata(self):
        """
        Returns
        -------
        dict
          keys and values are arbitrary
        """
        raise NotImplementedError

    def _get_content_metadata(self):
        """Get ALL metadata for all dataset content.

        Possibly limited to the paths given to the extractor.

        Returns
        -------
        generator((location, metadata_dict))
        """
        raise NotImplementedError
