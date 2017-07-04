# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Metadata (key) definitions"""


common_key_defs = {
    "@vocab": "http://schema.org/",
    "doap": "http://usefulinc.com/ns/doap#",
    "author": "schema:author",
    "audience": "doap:audience",
    "citation": "schema:citation",
    "contributors": "schema:contributor",
    "description": "schema:description",
    "homepage": "doap:homepage",
    "issuetracker": "doap:bug-database",
    "keywords": "schema:keywords",
    "license": "http://www.w3.org/1999/xhtml/vocab#license",
    "location": "schema:location",
    "maintainer": "doap:maintainer",
    "name": "schema:name",
    "shortdescription": "doap:shortdesc",
    "type": "schema:type",
    "version": "doap:Version",
    "conformsto": "dcterms:conformsTo",
    "fundedby": "foaf:fundedBy",
    "haspart": "dcterms:hasPart",
    "ispartof": "dcterms:isPartOf",
    "isversionof": "dcterms:isVersionOf",
    "modified": "dcterms:modified",
    "sameas": "schema:sameAs",
}
