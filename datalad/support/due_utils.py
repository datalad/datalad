#emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*- 
#ex: set sts=4 ts=4 sw=4 noet:
"""
Support functionality for using DueCredit
"""

# Note Text was added/exposed only since DueCredit 0.6.5
from .due import due, Doi, Url, Text

import logging
lgr = logging.getLogger('datalad.duecredit')


# Ad-hoc list of candidate metadata fields and corresponding
# DueCredit entries. First hit will win it all.
# In the future (TODO) extractors should provide API to provide
# reference(s). Order of extractors from config should be preserved
# and define precedence.
# Field for citation, Field for Description, DueCredit Entry.
CITATION_CANDIDATES = [
    ('bids.DatasetDOI', 'bids.name', Doi),  # our best guess I guess
    ('bids.HowToAcknowledge', 'bids.name', Text),
    # ('bids.citation', Text), # non-standard!
    # ('bids.ReferencesAndLinks', list) #  freeform but we could detect
    #                                   #  URLs, DOIs, and for the rest use Text
    # ('datacite.?'  # ?
    # ('frictionless_datapackage.?'  # ?
    # ('frictionless_datapackage.homepage'  # ?
    (None, None, None)  # Catch all so we leave no one behind
]


# Not worth being a @datasetmethod at least in this shape.
# Could in principle provide rendering of the citation(s) etc
# using duecredit
def duecredit_dataset(dataset):
    """Duecredit cite a dataset if Duecredit is active

    ATM it is an ad-hoc implementation which largely just supports
    extraction of citation information from BIDS extractor
    (datalad-neuroimaging extension) only ATM.
    Generic implementation would require minor harmonization and/or
    support of extraction of relevant information by each extractor.
    """

    res = dataset.metadata(
        reporton='datasets',  # Interested only in the dataset record
        result_renderer=None,  # No need
        return_type='item-or-list'  # Expecting a single record
    )

    if not isinstance(res, dict):
        lgr.debug("Got record which is not a dict, no duecredit for now")
    metadata = res.get('metadata', {})

    # Descend following the dots -- isn't there a helper already - TODO?
    def get_field(struct, field):
        if not field:
            return None
        value = struct
        for subfield in field.split('.'):
            value = value.get(subfield, None)
            if not value:
                return None
        return value

    for cite_field, desc_field, cite_type in CITATION_CANDIDATES:
        cite_rec = get_field(metadata, cite_field)
        if cite_field is not None:
            if not cite_rec:
                continue
            # we found it! ;)
        else:
            # Catch all
            cite_rec = "DataLad dataset at %s" % dataset.path

        desc = None
        if desc_field:
            desc = get_field(metadata, desc_field)
        desc = desc or "DataLad dataset %s" % dataset.id

        # DueCredit's path defines groupping of entries, so with
        # "datalad." we bring them all under datalad's roof!
        # And as for unique suffix, there is no better one but the ID,
        # but that one is too long so let's take the first part of UUID
        path = "datalad:%s" % (dataset.id.split('-', 1)[0])

        try:
            due.cite(
                (cite_type or Text)(cite_rec),
                path=path,
                version=dataset.repo.describe(),
                description=desc
            )
            break  # we are done. TODO: should we continue? ;)
        except Exception as exc:
            # who knows what could go wrong with DueCredit!?
            lgr.debug("DueCredit .cite caused %s", exc_str(exc))
