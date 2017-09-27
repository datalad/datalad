# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Metadata definitions"""

# identifiers that defines an ontology as a whole
ontology_id = 'http://edamontology.org/data_2338'

# this is the cannonical version string of Datalad's current metadata scheme
version = '2.0'

# for maximum compatibility with git-annex' metadata setup, _keys_ in this
# dictionary should be all lower-case, and be limited to alphanumerics, plus
# '_', '-', and '.' -- except for JSON-LD keywords (which start with '@' and
# will be ignored in the context of git-annex metadata
common_defs = {
    "schema": {
        'def': "http://schema.org/",
        'descr': 'base vocabulary',
        'type': ontology_id},
    "dcterms": {
        'def': "http://purl.org/dc/terms/",
        'descr': 'DCMI metadata terms',
        'type': ontology_id},
    "dctype": {
        'def': "http://purl.org/dc/dcmitype/",
        'descr': 'DCMI Type Vocabulary',
        'type': ontology_id},
    "doap": {
        'def': "http://usefulinc.com/ns/doap#",
        'descr': 'ontology for the description of a project',
        'type': ontology_id},
    "pato": {
        'def': "http://purl.obolibrary.org/obo/PATO_",
        'descr': 'Vocabulary of phenotypic qualities',
        'type': ontology_id},
    "uo": {
        'def': "http://purl.obolibrary.org/obo/UO_",
        'descr': "Units of Measurement Ontology",
        'type': ontology_id},
    "author": {
        'def': "schema:author",
        'descr': 'author of some resource'},
    "audience": {
        'def': "doap:audience",
        'descr': 'target audience description'},
    "citation": {
        'def': "schema:citation",
        'descr': 'reference to another creative work, such as a scholarly article'},
    "contributors": {
        'def': "schema:contributor",
        'descr': 'secondary author of a resource'},
    "description": {
        'def': "schema:description",
        'descr': 'description of a resource'},
    "homepage": {
        'def': "doap:homepage",
        'descr': 'homepage associated with a resource'},
    "issuetracker": {
        'def': "doap:bug-database",
        'descr': 'location of an issue tracker for a resource'},
    "tag": {
        'def': "schema:keywords",
        'descr': 'tag or keyword (often multiple) for a resource'},
    "license": {
        'def': "http://www.w3.org/1999/xhtml/vocab#license",
        'descr': 'licence or usage terms for a resource'},
    "location": {
        'def': "schema:location",
        'descr': 'location where a resource is available'},
    "maintainer": {
        'def': "doap:maintainer",
        'descr': 'maintainer of a resource'},
    "name": {
        'def': "schema:name",
        'descr': 'name of a resource'},
    "shortdescription": {
        'def': "doap:shortdesc",
        'descr': 'sort description or summary or title of a resource'},
    # wondering why there is no title, eh?
    # MIH: we have name and short description
    #      adding title seems superfluous
    #"title": "dcterms:title",
    "subject": {
        'def': 'dcterms:subject',
        'descr': 'topic of a resource, best practice is to use a controlled vocabulary'},
    "type": {
        'def': "schema:type",
        'descr': 'type or category of a resource (e.g. file, dataset)'},
    "unit": {
        'def': 'uo:0000000',
        'descr': 'standardized quantity of a physical quality'},
    "version": {
        'def': "doap:Version",
        'descr': 'version of a resource'},
    "conformsto": {
        'def': "dcterms:conformsTo",
        'descr': 'reference to a standard to which the described resource conforms'},
    "fundedby": {
        'def': "foaf:fundedBy",
        'descr': 'reference to an entity that provided funding for a resource'},
    "haspart": {
        'def': "dcterms:hasPart",
        'descr': 'related resource that is physically/logically included in a resource'},
    "ispartof": {
        'def': "dcterms:isPartOf",
        'descr': 'related resource in which a resource is physically/logically included'},
    "isversionof": {
        'def': "dcterms:isVersionOf",
        'descr': 'related resource of which the a resource is a version, edition, or adaptation'},
    "modified": {
        'def': "dcterms:modified",
        'descr': 'date on which the resource was changed'},
    "sameas": {
        'def': "schema:sameAs",
        'descr': "URL of a web page that unambiguously indicates a resource's identity"},
}
