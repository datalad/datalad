# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""NIDM metadata extractor"""

import logging
lgr = logging.getLogger('datalad.metadata.extractors.nidm')

from datalad.support.json_py import loads as json_loads
from datalad.metadata.extractors.base import BaseMetadataExtractor
from nidm.experiment.tools.BIDSMRI2NIDM import bidsmri2project


class MetadataExtractor(BaseMetadataExtractor):
    # this extractor instance knows:
    #   self.ds -- an instance of the dataset it shall operate on
    #   self.paths -- a list of paths within the dataset from which
    #                 metadata should be extracted, pretty much up to
    #                 the extractor if those those paths are used. They are
    #                 provided to avoid duplicate directory tree traversal
    #                 when multiples extractors are executed
    def get_metadata(self, dataset, content):
        # function gets two flags indicating whether to extract dataset-global
        # and/or content metadata

        # function returns a tuple
        # item 1: dict with dataset-global metadata (e.g. a NIDM blob)
        #         should come with a JSON-LD context for that blob, context
        #         is preserved during aggregation
        # item 2: generator yielding metadata dicts for each (file) path in the
        #         dataset. When querying aggregated metadata for a file, the dataset's
        #         JSON-LD context is assigned to the metadata dict, hence file metadata
        #         should not be returned with individual/repeated contexts, but rather
        #         the dataset-global context should provide all definitions
        nidm = bidsmri2project(self.ds.path)
        return json_loads(nidm.serializeJSONLD()), []
