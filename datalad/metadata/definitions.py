# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Metadata definitions"""

# identifiers that defines an ontology as a whole
vocabulary_id = 'http://purl.org/dc/dcam/VocabularyEncodingScheme'

# this is the canonical version string of DataLad's current metadata scheme
version = '2.0'

# for maximum compatibility with git-annex' metadata setup, _keys_ in this
# dictionary should be all lower-case, and be limited to alphanumerics, plus
# '_', '-', and '.' -- except for JSON-LD keywords (which start with '@' and
# will be ignored in the context of git-annex metadata
common_defs = {
    # ontologies/external vocabularies
    "schema": {
        'def': "http://schema.org/",
        'descr': 'base vocabulary',
        'type': vocabulary_id},
    "dcterms": {
        'def': "http://purl.org/dc/terms/",
        'descr': 'DCMI metadata terms',
        'type': vocabulary_id},
    "dctype": {
        'def': "http://purl.org/dc/dcmitype/",
        'descr': 'DCMI Type Vocabulary',
        'type': vocabulary_id},
    "doap": {
        'def': "http://usefulinc.com/ns/doap#",
        'descr': 'vocabulary for the description of a project',
        'type': vocabulary_id},
    "foaf": {
        'def': "http://xmlns.com/foaf/spec/#term_",
        'descr': 'vocabulary for describing (social) networks',
        'type': vocabulary_id},
    "idqa": {
        'def': "http://purl.obolibrary.org/obo/ID_",
        'descr': 'vocabulary for Image and Data Quality Assessment for scientific data management',
        'type': vocabulary_id},
    "mime": {
        'def': "https://www.iana.org/assignments/media-types/",
        'descr': 'IANA media types, see https://www.iana.org/assignments/media-types/media-types.xhtml',
        'type': vocabulary_id},
    "pato": {
        'def': "http://purl.obolibrary.org/obo/PATO_",
        'descr': 'Vocabulary of phenotypic qualities',
        'type': vocabulary_id},
    "time": {
        'def': 'https://www.w3.org/TR/owl-time/#',
        'descr': 'ontology of temporal concepts',
        'type': vocabulary_id},
    "uo": {
        'def': "http://purl.obolibrary.org/obo/UO_",
        'descr': "Units of Measurement Ontology",
        'type': vocabulary_id},
    # individually defined terms
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
    "comment": {
        'def': 'http://purl.obolibrary.org/obo/NCIT_C25393',
        'descr': 'A written explanation, or observation'},
    "description": {
        'def': "schema:description",
        'descr': 'description of a resource'},
    'format': {
        'def': 'http://purl.org/dc/elements/1.1/format',
        'descr': 'file format, physical medium, or dimensions of the resource.'},
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
        'descr': 'short description or summary or title of a resource'},
    # wondering why there is no title, eh?
    # MIH: we have name and short description
    #      adding title seems superfluous
    #"title": "dcterms:title",
    "subject": {
        'def': 'dcterms:subject',
        'descr': 'topic of a resource, best practice is to use a controlled vocabulary'},
    # TODO why not JSON-LD @type instead, an annexed file is type 'file' anyways
    "type": {
        'def': "dcterms:type",
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
