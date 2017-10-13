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
from datalad.metadata import is_implicit_metadata
from datalad.metadata.parsers.base import BaseMetadataParser
from datalad.metadata import _get_base_dataset_metadata


# XXX could be moved to aggregate parser...
def _adjust_subdataset_location(meta, subds_relpath):
    # find implicit meta data for all contained subdatasets
    for m in meta:
        # skip non-implicit
        if not is_implicit_metadata(m):
            continue
        # prefix all subdataset location information with the relpath of this
        # subdataset
        if 'dcterms:hasPart' in m:
            parts = m['dcterms:hasPart']
            if not isinstance(parts, list):
                parts = [parts]
            for p in parts:
                if 'location' not in p:
                    continue
                loc = p.get('location', subds_relpath)
                if loc != subds_relpath:
                    p['location'] = opj(subds_relpath, loc)


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
        base_meta = _get_base_dataset_metadata(dsid if dsid else self.ds.id)
        meta = [base_meta]
        basepath = opj(self.ds.path, '.datalad', 'meta')
        parts = []
        for subds_meta_fname in self.get_core_metadata_filenames():
            # get the part between the 'meta' dir and the filename
            # which is the subdataset mountpoint
            subds_path = subds_meta_fname[len(basepath) + 1:-10]
            if not subds_path:
                # this is a potentially existing cache of the native meta data
                # of the superdataset, not for us...
                continue
            submeta_info = {
                'location': subds_path}
            # load aggregated meta data
            subds_meta = jsonload(subds_meta_fname)
            # we cannot simply append, or we get weired nested graphs
            # proper way would be to expand the JSON-LD, extend the list and
            # compact/flatten at the end. However assuming a single context
            # we can cheat.
            subds_meta = _simplify_meta_data_structure(subds_meta)
            _adjust_subdataset_location(subds_meta, subds_path)
            # sift through all meta data sets look for a meta data set that
            # knows about being part of this dataset, so we record its @id as
            # part
            for md in subds_meta:
                cand_id = md.get('dcterms:isPartOf', None)
                if cand_id == dsid and '@id' in md:
                    submeta_info['@id'] = md['@id']
                    break

            if subds_meta:
                meta.extend(subds_meta)
            parts.append(submeta_info)
        if len(parts):
            if len(parts) == 1:
                parts = parts[0]
            base_meta['dcterms:hasPart'] = parts

        return meta
