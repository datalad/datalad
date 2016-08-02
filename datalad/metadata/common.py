# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Common metadata definitions"""

# exhaustive list of metadata predicates recognized by datalad
# keep sorted by key
predicates = {
    # A bibliographic reference for the resource (ideally a DOI)
    'citation': '<http://purl.org/dc/terms/bibliographicCitation>',
    # An established standard to which the described resource conforms
    # (e.g. BIDS, referenced by the DOI 10.1038/sdata.2016.44; or some other identifier
    # of the respective standard)
    'conformsto': '<http://purl.org/dc/terms/conformsTo>',
    # An entity responsible for making contributions to the resource. Object could be literal name
    # or proper person node if enough information is available.
    'contributor': '<http://purl.org/dc/elements/1.1/contributor>',
    # An entity primarily responsible for making the resource (where the resource is the datalad dataset)
    'creator': '<http://purl.org/dc/elements/1.1/creator>',
    # An account of the resource. Description may include but is not limited to: an abstract, a table of
    # contents, a graphical representation, or a free-text account of the resource.
    'description': '<http://purl.org/dc/elements/1.1/description>',
    # An organization funding a project or person, or some literal.
    'fundedby': '<http://xmlns.com/foaf/spec/#term_fundedBy>',
    # An unambiguous reference to the resource within a given context. Could be a DOI, an accession number,
    # or similar.
    'identifier': '<http://purl.org/dc/terms/identifier>',
    # A legal document giving official permission to do something with the resource. Ideally a link (e.g.
    # https://opensource.org/licenses/MIT), but also literal label, or even full text are possible
    'license': '<http://purl.org/dc/terms/license>',
    # A name for some thing, usually a simple string literal.
    'name': '<http://xmlns.com/foaf/spec/#term_name>',
    # An entity responsible for making the resource available. Either a link (e.g. http://datalad.org) or
    # a person-, organization-, or service-node..
    'publisher': '<http://purl.org/dc/terms/publisher>',
    # A person or organization owning or managing rights over the resource. Similar to 'contributor'.
    'rightsholder': '<http://purl.org/dc/terms/rightsHolder>',
    # The topic of the resource. Typically, the subject will be represented using keywords, key phrases,
    # or classification codes. Recommended best practice is to use a controlled vocabulary.
    'subject': '<http://purl.org/dc/terms/subject>',
    # A name given to the resource.
    'title': '<http://purl.org/dc/terms/title>',
    # The nature or genre of the resource. If nothing better is available this should be http://purl.org/dc/dcmitype/Dataset
    'type': '<http://purl.org/dc/terms/type>',
}

# some metadata objects recognized by datalad
# keep sorted by key
objects = {
    # Data encoded in a defined structure.foaf
    'dataset': '<http://purl.org/dc/dcmitype/Dataset>',
    # Any kind of people, dead or alive.
    'person': '<http://xmlns.com/foaf/spec/#term_Person>',
    # An organization like social instititutions such as companies, societies etc.
    'organization': '<http://xmlns.com/foaf/spec/#term_Organization>',
}
