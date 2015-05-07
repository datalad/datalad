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

from rdflib import Graph, URIRef, Literal
from rdflib.namespace import RDF, FOAF
import rdflib.namespace



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
        pass


class DefaultHandler(MetadataHandler):

    def __init__(self, path):
        super(DefaultHandler, self).__init__(path)

    def get_graph(self):
        meta = Graph()
        # look for standard files and
        # and build triples to add to the graph

        # either take all other files or a specific one like 'metadata'
        # and try whether we can read it.

        ######temporarily do just something valid:
        meta.parse(opj(self._path, 'metadata'))

        # add to the graph (join at handles' node?! => in Handle-class)
        # TODO: How to this? Check rdflib for such operations.

        return meta

    def set(self, meta):
        if not isinstance(meta, Graph):
            lgr.error("Argument is not a Graph: %s" % type(meta))
            raise TypeError("Argument is not a Graph: %s" % type(meta))

        # as above: just store for now. Has to be refined later on, regarding
        # what to store where.
        meta.serialize(opj(self._path, 'metadata'), format="turtle")

        # TODO: Where to commit?

