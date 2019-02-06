# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Metadata extractor for custom (JSON-LD) metadata contained in a dataset"""

from datalad.metadata.extractors.base import BaseMetadataExtractor

import logging
lgr = logging.getLogger('datalad.metadata.extractors.custom')
from datalad.utils import (
    assure_list,
)

from datalad.support.json_py import load as jsonload
# TODO test the faith of this one
from datalad.metadata.definitions import version as vocabulary_version

from ... import utils as ut


class MetadataExtractor(BaseMetadataExtractor):
    def _get_dataset_metadata(self):
        # which files to look at
        cfg_srcfiles = self.ds.config.obtain(
            'datalad.metadata.custom-dataset-source',
            [])
        cfg_srcfiles = assure_list(cfg_srcfiles)
        # OK to be always POSIX
        srcfiles = ['.datalad/metadata/custom.json'] \
            if not cfg_srcfiles else cfg_srcfiles
        dsmeta = {}
        for srcfile in srcfiles:
            # RF to self.ds.pathobj when part of -core
            abssrcfile = ut.Path(self.ds.path) / ut.PurePosixPath(srcfile)
            # TODO get annexed files
            if not abssrcfile.exists():
                # nothing to load
                # warn if this was configured
                if srcfile in cfg_srcfiles:
                    # TODO make this an impossible result, when
                    # https://github.com/datalad/datalad/issues/3125
                    # is resolved
                    lgr.warn(
                        'configured custom metadata source is not available '
                        'in %s: %s',
                        self.ds, srcfile)
                continue
            lgr.debug('Load custom metadata from %s', abssrcfile)
            meta = jsonload(str(abssrcfile))
            dsmeta.update(meta)
        return dsmeta

    def _get_content_metadata(self):
        return []
