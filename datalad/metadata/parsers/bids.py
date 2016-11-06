# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""BIDS metadata parser (http://bids.neuroimaging.io)"""


from re import compile
from datalad.support.json_py import load as jsonload
from datalad.metadata.parsers.base import BaseMetadataParser
from datalad.utils import assure_list


props = {
    compile(r'.*_T1w.nii.gz$'): {
        'contentType': {'@id': 'neurolex:nlx_156813'},
        'ShortDescription': 'T1-weighted MRI 3D image',
    },
    compile(r'.*_T2w.nii.gz$'): {
        'contentType': {'@id': 'neurolex:nlx_156812'},
        'ShortDescription': 'T2-weighted MRI 3D image',
    },
}


class MetadataParser(BaseMetadataParser):
    _core_metadata_filenames = ['dataset_description.json']
    cfg_section = 'datalad.metadata.parser.bids.report'

    def get_metadata(self, ds_identifier=None, full=False):
        meta = []
        base_meta = self._get_base_metadata_dict(ds_identifier)
        bids = jsonload(
            self.get_core_metadata_filenames()[0])

        # TODO maybe normalize labels of standard licenses to definition URIs
        # perform mapping
        for bidsterm, dataladterm in (('Name', 'Name'),
                                      ('License', 'License'),
                                      ('Authors', 'Author'),
                                      ('ReferencesAndLinks', 'Citation'),
                                      ('Funding', 'fundedBy'),
                                      ('Description', 'Description')):
            if bidsterm in bids:
                base_meta[dataladterm] = bids[bidsterm]
        compliance = assure_list(base_meta.get('conformsTo', []))
        # special case
        if bids.get('BIDSVersion'):
            compliance.append(
                'http://bids.neuroimaging.io/bids_spec{}.pdf'.format(
                    bids['BIDSVersion'].strip()))
        else:
            compliance.append('http://bids.neuroimaging.io')
        base_meta['conformsTo'] = compliance
        meta.append(base_meta)

        if self.ds.config.getbool(self.cfg_section, 'fileproperties', True):
            ds_meta, file_meta = self._get_file_metadata()
            # update dataset dict with info gathered from files
            base_meta.update(ds_meta)
            if len(file_meta):
                meta.extend(file_meta)
        return meta

    def _get_file_metadata(self):
        ds_meta = {}
        keywords = set()
        parts = set()
        file_meta = []
        for key, file_ in self.get_filekey_mapping().items():
            # check any defined property definition
            for prop in props:
                if prop.match(file_):
                    parts.add(key)
                    finfo = self._get_base_metadata_dict(key)
                    finfo.update(props[prop])
                    file_meta.append(finfo)
                    # collect unique short descriptions as keywords
                    keywords.add(finfo['ShortDescription'])
        if len(keywords):
            ds_meta['Keywords'] = sorted(list(keywords))
        if len(parts):
            ds_meta['hasParts'] = [{'@id': p} for p in sorted(parts)]
        return ds_meta, file_meta
