# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Parser for datalad's own aggregated metadata"""

from os.path import join as opj

from datalad.utils import find_files
from datalad.support.json_py import load as jsonload
from datalad.metadata import _simplify_meta_data_structure
from datalad.metadata import _adjust_subdataset_location
from datalad.metadata.parsers.base import BaseMetadataParser


class MetadataParser(BaseMetadataParser):
    def get_core_metadata_filenames(self):
        return list(find_files(
            'meta\.json',
            topdir=opj(self.ds.path, '.datalad', 'meta'),
            exclude=None,
            exclude_vcs=False,
            exclude_datalad=False,
            dirs=False))

    def get_metadata(self, dsid=None, full=False):
        meta = []
        basepath = opj(self.ds.path, '.datalad', 'meta')
        for subds_meta_fname in self.get_core_metadata_filenames():
            # get the part between the 'meta' dir and the filename
            # which is the subdataset mountpoint
            subds_path = subds_meta_fname[len(basepath) + 1:-10]
            # load aggregated meta data
            subds_meta = jsonload(subds_meta_fname)
            # we cannot simply append, or we get weired nested graphs
            # proper way would be to expand the JSON-LD, extend the list and
            # compact/flatten at the end. However assuming a single context
            # we can cheat.
            subds_meta = _simplify_meta_data_structure(subds_meta)
            _adjust_subdataset_location(subds_meta, subds_path)
            meta.extend(subds_meta)
        return meta
