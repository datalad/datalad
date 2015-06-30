# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
""" Handlers to read and write metadata
"""

import logging
from os.path import join as opj
from abc import ABCMeta, abstractmethod

from rdflib import Graph, Literal, Namespace, BNode
from rdflib.namespace import RDF, FOAF
from rdflib.exceptions import ParserError

# define datalad namespace:
DLNS = Namespace('http://www.datalad.org/terms/')
"""Namespace for datalad rdf triples.
"""

lgr = logging.getLogger('datalad.metadata')


class MetadataHandler(object):
    """Interface for metadata handlers.

    To be implemented by any handler, that aims to provide support for a
    certain metadata format.
    """
    __metaclass__ = ABCMeta

    @abstractmethod
    def get_graph(self, uri=None, class_=None, file_=None, identifier=None,
                  data=None):
        """Get a representation of the metadata of a resource.

        This should return a (named) rdflib.Graph containing the metadata. This
        graph is required to contain a certain set of statements, that are
        defined as the "datalad handle descriptor" or
        "datalad collection descriptor" respectively in
        'docs/datalad-metadata.rst'.
        The datalad namespace (http://www.datalad.org/terms/) is available as
        a rdflib.namespace `DLNS`.

        Parameters:
        -----------
        uri: rdflib.URIRef
            the resource, the metadata is about. This is needed to have this
            as a node (kind of a root) in the graph. Will usually be the uri of
            a collection or handle repository.
        class_: rdflib.term.URIRef
            the class of the resource at `uri`, i.e. the term to be used to
            describe this resource. For now, it's either `DLNS.Handle` or
            `DLNS.Collection`.
        file_: str or list of str
            path to the file or directory containing the metadata. May also be
            a list of files.
        identifier: str
            optionally used to create a named graph
        data: str
            optionally parse `data` instead of any file

        Note: Either `file_` or `data` must be provided.
        """
        pass

    def set(self, meta, file_):
        """Write metadata to file.

        Note: By now, this doesn't need to be implemented, since the metadata
        is provided by the handle/collection publisher/maintainer in the very
        format the handler is implementing. So, changes should probably be done
        without datalad. The only thing datalad writes metadata to, is a cache.
        This may change once we discover it's needed.

        Parameters:
        -----------
        meta: rdflib.Graph
        file_: str or list of str
            path to the file or directory containing the metadata. May also be
            a list of files.
        """
        raise NotImplementedError

import json
import dateutil.parser


class JSONExampleHandler(MetadataHandler):
    """Implementation of a very simple JSON metadata format.

    Just an example to show, how things are supposed to work.
    For this format a JSON file, named 'metadata.json' is accepted and may
    contain some keys that are 'translated' to datalad rdf-representation as
    follows:

    'authors': a list of authors' names
        (There is no split for first and last name here)
        translates to datalad property 'authoredBy'

    'comment':
        translates to datalad property 'description'

    'date':
        translates to datalad property 'released'

    'name':
        translates to datalad property 'title'

    'release':
        translates to datalad property 'version'

    Note: These datalad properties as well as this format are just a demo.
    Nothing well defined, nothing thoughtfully considered to be reasonable.
    Just demonstrating the principle.

    See also RDFExampleHandler for comparison.
    """

    def __init__(self, uri, class_):
        super(JSONExampleHandler, self).__init__(uri, class_)

    def get_graph(self, file_='metadata.json', identifier=None, data=None):
        meta = Graph(identifier=identifier)
        meta.bind('dlns', DLNS)
        meta.bind('foaf', FOAF)

        if data is None:
            json_dict = json.load(open(opj(self._uri, file_), 'r'))
        else:
            json_dict = json.loads(data)

        for author in json_dict['authors']:
            # Create a node for the author;
            # could also be a URIRef in case a homepage is provided or sth.
            authors_node = BNode()
            meta.add((authors_node, RDF.type, FOAF.Person))
            meta.add((authors_node, FOAF.name, Literal(author)))

            # make it a author of the thing (to be queried for):
            meta.add((self._class, DLNS.authoredBy, authors_node))
            # Note: Actually, needs to be a rdf list (first, rest)
            # Not important for now.

        if json_dict['comment']:
            meta.add((self._class, DLNS.description,
                      Literal(json_dict['comment'])))
        if json_dict['date']:
            date = dateutil.parser.parse(json_dict['date'])
            meta.add((self._class, DLNS.released, Literal(date)))
        if json_dict['name']:
            meta.add((self._class, DLNS.title, Literal(json_dict['name'])))
        if json_dict['release']:
            meta.add((self._class, DLNS.version, Literal(json_dict['release'])))
        for t in json_dict['topic']:
            meta.add((self._class, DLNS.tag, Literal(json_dict['topic'])))

        return meta


class RDFExampleHandler(MetadataHandler):
    """An example to show an implementation of a MetadataHandler.

    By now just accepts a turtle file named 'metadata.rdf' containing the
    'datalad descriptor' implicitly defined in `JSONExampleHandler`.
    """

    def __init__(self, uri, class_):
        super(RDFExampleHandler, self).__init__(uri, class_)

    def get_graph(self, file_='metadata.rdf', identifier=None, data=None):
        meta = Graph(identifier=identifier)

        if data is None:
            try:
                meta.parse(opj(self._uri, file_), format="turtle")
            except IOError, ioe:
                lgr.warning("Failed to read metadata file: %s" % ioe)
            except ParserError, pe:
                lgr.error("Failed to parse metadata file: %s" % pe)
        else:
            try:
                meta.parse(data=data, format="turtle")
            except ParserError, pe:
                lgr.error("Failed to parse metadata file: %s" % pe)

        return meta

    def set(self, meta, file_='metadata.rdf'):
        if not isinstance(meta, Graph):
            lgr.error("Argument is not a Graph: %s" % type(meta))
            raise TypeError("Argument is not a Graph: %s" % type(meta))

        meta.serialize(opj(self._uri, file_), format="turtle")


class DefaultHandler(MetadataHandler):
    # DefaultHandler may be should scan for file types and instantiate a
    # Handler for each; then join the graphs. Would probably need a method to
    # read a single file in the handler interface.

    def __init__(self, uri, class_):
        super(DefaultHandler, self).__init__(uri, class_)

    def get_graph(self, file_=None, identifier=None, data=None):
        return Graph(identifier=identifier)

    def set(self, meta, file_=None):
        pass


class CacheHandler(MetadataHandler):
    """Handler to care for collection's metadata cache, managed by datalad

    By now stores the cached graph just as a turtle-file. This may change,
    depending on what turns out to be the fastest parseable format.
    """
    # TODO: May be to be (re-)implemented, once we decided about a
    # 'datalad descriptor'

    def __init__(self):
        super(CacheHandler, self).__init__()

    def get_graph(self, uri=None, class_=None, file_=None, identifier=None,
                  data=None):
        meta = Graph(identifier=identifier)
        if data is None:
            meta.parse(file_, format="turtle")
        else:
            meta.parse(data=data, format="turtle")
        return meta

    def set(self, meta, file_=None):
        meta.serialize(file_, format="turtle")


class PlainTextHandler(MetadataHandler):

    def __init__(self, uri, class_):
        super(PlainTextHandler, self).__init__(uri, class_)

    def get_graph(self, file_=None, identifier=None, data=None):
        meta = Graph(identifier=identifier)

        self._uri
        self._class


# TODO: Things probably to add:
# class 'real' JSONHandler
# class W3CDescriptorHandler