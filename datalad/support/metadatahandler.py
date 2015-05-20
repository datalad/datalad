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
from abc import ABCMeta, abstractmethod, abstractproperty

from rdflib import Graph, URIRef, Literal, Namespace, BNode
from rdflib.namespace import RDF, FOAF, RDFS
from rdflib.exceptions import ParserError

# define datalad namespace:
DLNS = Namespace('http://www.datalad.org/terms/')

lgr = logging.getLogger('datalad.metadata')


class MetadataHandler(object):
    """Interface for metadata handlers.
    """
    __metaclass__ = ABCMeta

    # TODO: rdf datalad namespace for Collections, Handles, standard metadata
    # if possible, just use existing ones, like RDF.

    def __init__(self, path):
        """
        Parameters:
        -----------
        path: str
          directory to look for metadata files in.
        """
        self._path = path

    @abstractmethod
    def get_graph(self):
        pass

    @abstractmethod
    def set(self, meta):
        # TODO: Useful at all? For now, it seems to be needed for the internal
        # metadata cache only.
        pass


class DefaultHandler(MetadataHandler):
    # DefaultHandler may be should scan for file types and instantiate a
    # Handler for each; then join the graphs. Would probably need a method to
    # read a single file in the handler interface.

    def __init__(self, path):
        super(DefaultHandler, self).__init__(path)

    def get_graph(self):
        return Graph()

    def set(self, meta):
        pass


class RDFHandler(MetadataHandler):
    """By now accepts a file named 'metadata' containing arbitrary rdf-data.
    """

    def __init__(self, path):
        super(RDFHandler, self).__init__(path)

    def get_graph(self):
        meta = Graph()

        # TODO: May be (try to) read all files in self._path and join the
        # graphs:
        try:
            meta.parse(opj(self._path, 'metadata'))
        except IOError, ioe:
            lgr.warning("Failed to read metadata file: %s" % ioe)
        except ParserError, pe:
            lgr.error("Failed to parse metadata file: %s" % pe)

        return meta

    def set(self, meta):
        if not isinstance(meta, Graph):
            lgr.error("Argument is not a Graph: %s" % type(meta))
            raise TypeError("Argument is not a Graph: %s" % type(meta))

        # TODO: Check whether it is possible to get the format detected by
        # Graph.parse() and use it here.
        meta.serialize(opj(self._path, 'metadata'), format="turtle")


# class JSONHandler
# class PlainTextHandler
# class W3CDescriptorHandler