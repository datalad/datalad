# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil; coding: utf-8 -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test custom metadata extractor"""

from ....dataset import RevolutionDataset as Dataset
# API commands needed
from datalad.api import (
    rev_create,
    rev_save,
    aggregate_metadata,
)
from datalad.tests.utils import (
    with_tree,
    eq_,
    assert_status,
    assert_result_count,
    assert_in,
    assert_not_in,
)
from ....tests.utils import (
    assert_repo_status,
)
from simplejson import dumps as jsondumps

# some metadata to play with, taken from the examples of the google dataset
# search
# this is JSON+LD with plain schema.org terms
sample_jsonld = \
{
    "@context": "https://schema.org/",
    "@type": "Dataset",
    "name": "NCDC Storm Events Database",
    "description": "Storm Data is provided by the National Weather Service (NWS) and contain statistics on...",
    "url": "https://catalog.data.gov/dataset/ncdc-storm-events-database",
    "sameAs": "https://gis.ncdc.noaa.gov/geoportal/catalog/search/resource/details.page?id=gov.noaa.ncdc:C00510",
    "keywords": [
        "ATMOSPHERE > ATMOSPHERIC PHENOMENA > CYCLONES",
        "ATMOSPHERE > ATMOSPHERIC PHENOMENA > DROUGHT",
        "ATMOSPHERE > ATMOSPHERIC PHENOMENA > FOG",
        "ATMOSPHERE > ATMOSPHERIC PHENOMENA > FREEZE"
    ],
    "creator": {
        "@type": "Organization",
        "url":  "https://www.ncei.noaa.gov/",
        "name": "OC/NOAA/NESDIS/NCEI > National Centers for Environmental Information, NESDIS, NOAA, U.S. Department of Commerce",
        "contactPoint": {
            "@type": "ContactPoint",
            "contactType": "customer service",
            "telephone": "+1-828-271-4800",
            "email": "ncei.orders@noaa.gov"
        }
    },
    "includedInDataCatalog": {
        "@type": "DataCatalog",
        "name": "data.gov"
    },
    "distribution": [
        {
            "@type": "DataDownload",
            "encodingFormat": "CSV",
            "contentUrl": "http://www.ncdc.noaa.gov/stormevents/ftp.jsp"
        },
        {
            "@type": "DataDownload",
            "encodingFormat": "XML",
            "contentUrl": "http://gis.ncdc.noaa.gov/all-records/catalog/search/resource/details.page?id=gov.noaa.ncdc:C00510"
        }
    ],
    "temporalCoverage": "1950-01-01/2013-12-18",
    "spatialCoverage": {
        "@type": "Place",
        "geo": {
            "@type": "GeoShape",
            "box": "18.0 -65.0 72.0 172.0"
        }
    }
}

testmeta = {
    "@id": "magic",
    "name": "silence"
}


@with_tree(
    tree={
        '.datalad': {
            'metadata': {
                'custom.json': jsondumps(sample_jsonld)}},
        'down': {
            'customloc': jsondumps(testmeta)}})
def test_custom(path):
    ds = Dataset(path).rev_create(force=True)
    # enable custom extractor
    # use default location
    ds.config.add('datalad.metadata.nativetype', 'custom', where='dataset')
    ds.rev_save()
    assert_repo_status(ds.path)
    res = ds.aggregate_metadata()
    assert_status('ok', res)
    res = ds.metadata(reporton='datasets')
    assert_result_count(res, 1)
    dsmeta = res[0]['metadata']
    assert_in('custom', dsmeta)
    eq_(sample_jsonld, dsmeta['custom'])
    assert_not_in('@id', dsmeta['custom'])

    # overwrite default source location within something non-exiting
    # extraction does not blow up, but no metadata is reported
    ds.config.add(
        'datalad.metadata.custom-dataset-source',
        'nothere',
        where='dataset')
    ds.aggregate_metadata()
    res = ds.metadata(reporton='datasets')
    assert_result_count(res, 1)
    assert_not_in('custom', res[0]['metadata'])

    # overwrite default source location within something existing
    ds.config.set(
        'datalad.metadata.custom-dataset-source',
        # always POSIX!
        'down/customloc',
        where='dataset')
    ds.rev_save()
    ds.aggregate_metadata()
    res = ds.metadata(reporton='datasets')
    assert_result_count(res, 1)
    eq_(testmeta, res[0]['metadata']['custom'])

    # multiple source locations
    ds.config.add(
        'datalad.metadata.custom-dataset-source',
        # put back default
        '.datalad/metadata/custom.json',
        where='dataset')
    ds.rev_save()
    ds.aggregate_metadata()
    res = ds.metadata(reporton='datasets')
    assert_result_count(res, 1)
    eq_(
        # merge order: testmeta <- sample_jsonld
        dict(testmeta, **sample_jsonld),
        res[0]['metadata']['custom']
    )
