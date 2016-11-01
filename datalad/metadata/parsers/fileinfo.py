# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Parser for generic file-based information (mime types, etc...)
"""

from datalad.metadata import _get_base_metadata_dict
from datalad.support.annexrepo import AnnexRepo
from datalad.metadata.parsers.base import BaseMetadataParser


class MetadataParser(BaseMetadataParser):
    _metadata_compliance = "http://docs.datalad.org/metadata.html#v0-1"

    def has_metadata(self):
        # could check if there is at least one annexed file, but hey...
        repo = self.ds.repo
        return repo and isinstance(repo, AnnexRepo)

    def get_metadata(self, dsid=None, full=False):
        meta = []
        ds_meta = _get_base_metadata_dict(dsid)
        parts = []
        if not self.has_metadata():
            return meta
        repo = self.ds.repo
        files = repo.get_annexed_files()
        # TODO RF to do this with one annex call
        keys = [repo.get_file_key(f) for f in files]
        for key, file_ in zip(keys, files):
            finfo = {
                '@id': key,
                'Type': 'File',
                'Location': file_,
                'FileSize': repo.get_size_from_key(key),
            }
            # TODO actually insert a "magic"-based description, and
            # maybe a mimetype
            meta.append(finfo)
            parts.append({'@id': key})
        if len(parts):
            ds_meta['hasPart'] = parts
            meta.append(ds_meta)
        return meta
