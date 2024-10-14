#emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
#ex: set sts=4 ts=4 sw=4 et:
"""
Support functionality for using DueCredit
"""

import logging

from datalad.support.exceptions import CapturedException

from ..utils import (
    never_fail,
    swallow_logs,
)
# Note Text was added/exposed only since DueCredit 0.6.5
from .due import (
    Doi,
    Text,
    due,
)

lgr = logging.getLogger('datalad.duecredit')


# Ad-hoc list of candidate metadata fields and corresponding
# DueCredit entries. First hit will win it all.
# In the future (TODO) extractors should provide API to provide
# reference(s). Order of extractors from config should be preserved
# and define precedence.
# Citation Field(s), Description Field(s), Version Field(s), DueCredit Entry.
CITATION_CANDIDATES = [
    ('bids.DatasetDOI', 'bids.name', None, Doi),  # our best guess I guess
    ('bids.HowToAcknowledge', 'bids.name', None, Text),
    # ('bids.citation', Text), # non-standard!
    # ('bids.ReferencesAndLinks', list) #  freeform but we could detect
    #                                   #  URLs, DOIs, and for the rest use Text
    # CRCNS style datacite
    ('datacite.sameas', ('datacite.shortdescription', 'datacite.description'),
     'datacite.version', Doi),
    # ('frictionless_datapackage.?'  # ?
    # ('frictionless_datapackage.homepage'  # ?
    (None, None, None, None)  # Catch all so we leave no one behind
]


# Not worth being a @datasetmethod at least in this shape.
# Could in principle provide rendering of the citation(s) etc
# using duecredit
@never_fail  # For paranoid Yarik
def duecredit_dataset(dataset):
    """Duecredit cite a dataset if Duecredit is active

    ATM it is an ad-hoc implementation which largely just supports
    extraction of citation information from BIDS extractor
    (datalad-neuroimaging extension) only ATM.
    Generic implementation would require minor harmonization and/or
    support of extraction of relevant information by each extractor.
    """

    try:
        # probably with metalad RFing we would gain better control
        # over reporting of warnings etc, ATM the warnings are produced
        # directly within get_ds_aggregate_db_locations down below and
        # we have no other way but pacify all of them.
        with swallow_logs(logging.ERROR) as cml:
            res = dataset.metadata(
                reporton='datasets',  # Interested only in the dataset record
                result_renderer='disabled',  # No need
                return_type='item-or-list'  # Expecting a single record
            )
    except Exception as exc:
        lgr.debug(
            "Failed to obtain metadata for %s. Will not provide duecredit entry: %s",
            dataset, CapturedException(exc)
        )
        return

    if not isinstance(res, dict):
        lgr.debug("Got record which is not a dict, no duecredit for now")
        return

    metadata = res.get('metadata', {})

    # Descend following the dots -- isn't there a helper already - TODO?
    def get_field(struct, field):
        if isinstance(field, (tuple, list)):
            first = lambda values: (el for el in values if el)
            return next(first(get_field(struct, f) for f in field), None)
        if not field:
            return None
        # I think it is better to be case insensitive
        field = field.lower()
        value = struct
        for subfield in field.split('.'):
            # lower case all the keys
            value = {k.lower(): v for k, v in value.items()}
            value = value.get(subfield, None)
            if not value:
                return None
        return value

    for cite_field, desc_field, version_field, cite_type in CITATION_CANDIDATES:
        cite_rec = get_field(metadata, cite_field)
        if cite_field is not None:
            if not cite_rec:
                continue
            # we found it! ;)
        else:
            # Catch all
            cite_rec = "DataLad dataset at %s" % dataset.path

        desc = get_field(metadata, desc_field) if desc_field else None
        desc = desc or "DataLad dataset %s" % dataset.id

        # DueCredit's path defines grouping of entries, so with
        # "datalad." we bring them all under datalad's roof!
        # And as for unique suffix, there is no better one but the ID,
        # but that one is too long so let's take the first part of UUID
        path = "datalad:%s" % (dataset.id.split('-', 1)[0])

        version = get_field(metadata, version_field) if version_field else None
        version = version or dataset.repo.describe()

        due.cite(
            (cite_type or Text)(cite_rec),
            path=path,
            version=version,
            description=desc
        )
        return  # we are done. TODO: should we continue? ;)
