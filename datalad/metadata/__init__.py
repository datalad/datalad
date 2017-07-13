# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Metadata handling (parsing, storing, querying)"""


# TODO pretty much obsolete
def _get_base_dataset_metadata(ds_identifier):
    """Return base metadata as dict for a given ds_identifier
    """

    meta = {
        "@context": {
            "@vocab": "http://schema.org/",
            "doap": "http://usefulinc.com/ns/doap#",
        },
        # increment when changes to meta data representation are done
        "dcterms:conformsTo": "http://docs.datalad.org/metadata.html#v0-1",
    }
    if ds_identifier is not None:
        meta["@id"] = ds_identifier
    return meta
