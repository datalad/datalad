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

from rdflib import Graph, Literal, Namespace, BNode, URIRef
from rdflib.namespace import RDF, RDFS, FOAF, XSD, DCTERMS
from rdflib.exceptions import ParserError

# define needed namespaces:
DLNS = Namespace('http://www.datalad.org/terms/')
"""Namespace for datalad terms.
"""
PROV = Namespace('http://www.w3.org/ns/prov#')
DCAT = Namespace('http://www.w3.org/ns/dcat#')
DCTYPES = Namespace('http://purl.org/dc/dcmitype/>')
PAV = Namespace('http://purl.org/pav/')
EMP = Namespace('#')

lgr = logging.getLogger('datalad.metadata')


class MetadataImporter(object):
    """Base class for importers of various metadata formats.

    This abstract class has to be implemented, in order to provide datalad
    support for a certain metadata format. Besides the interface, enforced by
    this class, it provides basic functionality and data structure for that
    purpose.
    It provides a dictionary `self._graphs` to store imported rdf-graphs in
    as well as a default implementation to store them within handle or
    collection repositories.

    Note: If you are about to implement a derivation from this class, make sure
    you read datalad-metadata.rst first for a description of the
    'datalad descriptor' and the general approach to metadata in datalad.
    Furthermore, be aware that only `import_data` lacks a default implementation.
    """

    __metaclass__ = ABCMeta

    def __init__(self, target, about_class=None, about_uri=None):
        """Constructor

        Note: In case the metadata to be imported is about a handle or
        collection, the constructor initializes `self._graphs['datalad']`,
        which is to be used for the standard statements of the 'datalad
        descriptor'. You can add additional graphs to the `self._graphs`
        dictionary.

        Parameters:
        -----------
        target_class: HandleRepo or CollectionRepo
          the type of repo, the metadata is to be imported to;
          either "Handle" or "Collection"
          Note (todo): It may become handy at some point to have no target repo
          at all.
        about_class: str
          the kind of entity, the metadata is about. In case of "Handle" or
          "Collection" a corresponding datalad graph has to be generated.
          If the imported metadata is about a sub-entity of the repo's content,
          datalad doesn't know (and doesn't need to know) that class of things.
          In that case, it's up to the importer to decide, whether or not this
          class needs some special treatment.
        about_uri: str
          URI of the entity, the metadata is about. In case of handles or
          collections this may be the path to its repo in local file system or
          its url, if it is known by the caller. If it is about a collection or
          handle importing metadata about itself, it uses `DLNS.this` instead.
        """
        self._target = target
        self._about_class = about_class
        self._about_uri = about_uri

        self._graphs = dict()
        if self._about_class == 'Handle' or self._about_class == 'Collection':
            self._init_datalad_graph()

    def _init_datalad_graph(self):
        """Convenience method to init the datalad descriptor graph"""

        self._graphs['datalad'] = Graph()
        self._graphs['datalad'].bind('prov', PROV)
        self._graphs['datalad'].bind('dcat', DCAT)
        self._graphs['datalad'].bind('dctypes', DCTYPES)
        self._graphs['datalad'].bind('dct', DCTERMS)
        self._graphs['datalad'].bind('pav', PAV)
        self._graphs['datalad'].bind('foaf', FOAF)
        self._graphs['datalad'].bind('dlns', DLNS)
        self._graphs['datalad'].bind('', EMP)
        # TODO: Find a better prefix than ''. When stored, then parsed with
        # rdflib and stored again, it turns to the path of the file,
        # it was stored in!

        if self._about_class == 'Handle':
            self._graphs['datalad'].add((URIRef(self._about_uri),
                                         RDF.type, DLNS.Handle))
        elif self._about_class == 'Collection':
            self._graphs['datalad'].add((URIRef(self._about_uri),
                                         RDF.type, DLNS.Collection))

    @abstractmethod
    def import_data(self, files=None, data=None):
        """The actual import routine

        Has to be able to import data from files, given their paths, as well as
        just the content of the files provided as strings. The latter is
        necessary, in case the actual files are accessible via a remote of a
        repository only.

        This means: Either `files` or `data` has to be provided by the caller.

        Parameters:
        -----------
        files: str or list of str
          a path to the file or directory to be imported or a list containing
          such paths.
        data: str or list of str
        """
        pass

    @abstractmethod
    def store_data(self, path):
        """Store the imported metadata within a given directory

        This routine stores the metadata imported by `import_data` within the
        directory `path`. The datalad standard statements as described in
        'datalad-metadata.rst' have to be stored in a file called 'datalad.ttl'
        in turtle.
        Additional statements can be stored in additional files,
        also using turtle and the ending ".ttl". Any additional file can be
        read by datalad separately, allowing for smaller rdf-graphs to be build,
        whenever there is no need to have a runtime representation of all its
        metadata.

        The default implementation just stores every graph stored in
        `self._graphs['key']` in the file 'key.ttl'.

        Parameters:
        -----------
        path: str
          path to the directory to save the metadata in.
        """

        for key in self._graphs:
            self._graphs[key].serialize(opj(path, key + '.ttl'),
                                        format="turtle")