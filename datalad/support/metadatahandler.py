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
        pass


class DefaultHandler(MetadataHandler):

    def __init__(self, path):
        super(DefaultHandler, self).__init__(path)

    def get_graph(self, handle_path):
        # handle_path: by now, it's just self._path + '..'
        # But not sure yet, whether a Handler should know about a handle or be
        # more general. Let's see how this works with collections.
        # self._path could also be just some dir with metadata and no connection
        # to an actual handle.

        # TODO handle_path: Not needed. Just return a graph. It's name is needed
        # only at collection-level within its store.

        meta = Graph()
        # look for standard files and
        # and build triples to add to the graph

        # either take all other files or a specific one like 'metadata'
        # and try whether we can read it.

        # The following would read arbitrary rdf files, but how to connect this
        # general graph to the handle node, since we know nothing about it?
        try:
            meta.parse(opj(self._path, 'metadata'))
        except IOError:
            # File is not mandatory, so just ignore if it can't be read.
            pass

        # For now create a dummy graph for proof of concept:
        handle = URIRef(handle_path)
        meta.add((handle, RDF.type, DLNS.Handle))
        meta.add((handle, RDFS.comment, Literal("A handle with a dummy "
                                                  "metadata set.")))

        author = BNode()
        meta.add((author, RDF.type, FOAF.Person))
        meta.add((author, FOAF.name, Literal("Benjamin Poldrack")))
        meta.add((author, FOAF.mbox, URIRef("mailto:benjaminpoldrack@gmail.com")))

        meta.add((handle, FOAF.made, author))
        meta.add((author, FOAF.maker, handle))

        return meta

    def set(self, meta):
        # TODO: Useful at all? For now, it seems to be needed for the internal
        # metadata cache only.

        if not isinstance(meta, Graph):
            lgr.error("Argument is not a Graph: %s" % type(meta))
            raise TypeError("Argument is not a Graph: %s" % type(meta))

        # as above: just store for now. Has to be refined later on, regarding
        # what to store where.
        meta.serialize(opj(self._path, 'metadata'), format="turtle")

        # TODO: Where to commit? => would need knowledge about hte handle itself.
        # Commit in the handle!
        # But then other uses of these handlers are at least a little bit inconsistent.



# DefaultHandler may should scan for file types and instantiate a Handler for
# each; then join the graphs.

# class JSONHandler
# class RDFHandler
# class PlainTextHandler
# class W3CDescriptorHandler