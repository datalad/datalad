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
from os.path import join as opj, isdir, basename
from os import listdir
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
DCTYPES = Namespace('http://purl.org/dc/dcmitype/')
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
    Furthermore, be aware, that only `import_data` lacks a default implementation.
    """

    __metaclass__ = ABCMeta

    def __init__(self, target_class, about_class=None, about_uri=None):
        """Constructor

        Note: In case the metadata to be imported is about a handle or
        collection, the constructor initializes `self._graphs['datalad']`,
        which is to be used for the standard statements of the 'datalad
        descriptor'. You can add additional graphs to the `self._graphs`
        dictionary.

        Parameters:
        -----------
        target_class: str
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
        self._target_class = target_class
        self._about_class = about_class
        self._about_uri = URIRef(about_uri)

        self._graphs = dict()
        if self._about_class == 'Handle' or self._about_class == 'Collection':
            self._init_datalad_graphs()

    def _init_datalad_graphs(self):
        """Convenience method to init the datalad descriptor graph"""

        self._graphs['datalad'] = Graph()
        self._graphs['config'] = Graph()
        self._graphs['datalad'].bind('prov', PROV)
        self._graphs['datalad'].bind('dcat', DCAT)
        self._graphs['datalad'].bind('dctypes', DCTYPES)
        self._graphs['datalad'].bind('dct', DCTERMS)
        self._graphs['datalad'].bind('pav', PAV)
        self._graphs['datalad'].bind('foaf', FOAF)
        self._graphs['datalad'].bind('dlns', DLNS)
        self._graphs['config'].bind('dlns', DLNS)
        self._graphs['datalad'].bind('', EMP)
        self._graphs['config'].bind('', EMP)

        # TODO: Find a better prefix than ''. When stored, then parsed with
        # rdflib and stored again, it turns to the path of the file,
        # it was stored in!

        if self._about_class == 'Handle':
            self._graphs['datalad'].add((self._about_uri, RDF.type,
                                         DLNS.Handle))
        elif self._about_class == 'Collection':
            self._graphs['datalad'].add((self._about_uri, RDF.type,
                                         DLNS.Collection))

    @abstractmethod
    def import_data(self, files=None, data=None):
        """The actual import routine

        Importing means to read the data and generate a rdf-representation,
        that can be stored by calling `store_data`.
        Has to be able to import data from files, given their paths, as well as
        just the content of the files provided as strings. The latter is
        necessary, in case the actual files are accessible via a remote of a
        repository only, for example.
        This means: Either `files` or `data` has to be provided by the caller.

        Parameters:
        -----------
        files: str or list of str
          Either a path to the file or directory to be imported or a list
          containing paths to the files.
        data: dict of list of str
          a dictionary containing the metadata to be imported. The key is
          expected to be the file name and the value its content as a list of
          the file's lines as returned by `readlines()`.
        """
        pass

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


class PlainTextImporter(MetadataImporter):
    """Implements a simple plain text format

    An importer to provide support for basic metadata, based on simple text
    files. These files are:

    1. Any file, starting with "LICENSE". If there is a single line only, it is
    assumed to be an URI of the actual license. Otherwise it is treated as the
    text containing the actual license.

    2. Any file, starting with "README". This considered to be the description
    of the handle or collection. No further parsing is taking place at all.

    3. Any file, starting with "AUTHORS" or "CONTRIBUTORS".
    These file are expected to contain one author per line. This line is
    expected contain a name, optionally followed by an url or email address
    within '<' and '>'. If provided, the latter is treated as the identifier
    and therefore allows for identification across handles/collections.
    However, lines starting with '#' are ignored.
    """

    def __init__(self, target_class, about_class=None, about_uri=None):
        super(PlainTextImporter, self).__init__(target_class, about_class,
                                                about_uri)

    def import_data(self, files=None, data=None):
        """Parses the data and generates a rdf-representation



        Parameters:
        -----------
        files: str or list of str
          a path to the file or directory to be imported or a list containing
          such paths.
        data: dict of list of str
          a dictionary containing the metadata to be imported. The key is
          expected to be the file name and the value its content as a list of
          the file's lines as returned by `readlines()`.
        """

        authors = None
        readme = None
        license_ = None

        if files is not None:
            if not isinstance(files, list):  # single path
                if isdir(files):
                    files = listdir(files)

            for file_ in files:
                if not isdir(file_):
                    if file_.startswith(("AUTHORS", "CONTRIBUTORS")):
                        with open(file_, 'r') as f:
                            authors = f.readlines()
                    if file_.startswith("README"):
                        with open(file_, 'r') as f:
                            readme = f.readlines()
                    if file_.startswith("LICENSE"):
                        with open(file_, 'r') as f:
                            license_ = f.readlines()

        if data is not None:
            for key in data:
                if key.startswith(("AUTHORS", "CONTRIBUTORS")):
                    authors = data[key]
                if key.startswith("README"):
                    readme = data[key]
                if key.startswith("LICENSE"):
                    license_ = data[key]

        # now, creating the required rdf-statements:

        # if we are importing a repo's metadata into the repo itself,
        # this handle or collection is considered to be 'created' with datalad.
        # TODO: This behaviour is open to discussion, of course.
        # Not entirely sure yet, whether or not this is reasonable.
        if self._about_class == self._target_class:
            self._graphs['datalad'].add((EMP.datalad, RDF.type,
                                         PROV.SoftwareAgent))
            self._graphs['datalad'].add((EMP.datalad, RDFS.label,
                                         Literal("datalad")))
            self._graphs['datalad'].add((self._about_uri, PAV.createdWith,
                                         EMP.datalad))
            # TODO: datalad version and may be creation time

        # If the metadata is about a handle, we need to add a 'data entity',
        # that is contained in that handle. Due to the simplicity of this
        # format, we don't know about possibly existing sub-entities.
        # So, we are just stating: "There is something in it,
        # and it's some kind of dataset."
        if self._about_class == 'Handle':
            self._graphs['datalad'].add((EMP.content, RDF.type,
                                         DCTYPES.Dataset))
            self._graphs['datalad'].add((self._about_uri, DCTERMS.hasPart,
                                         EMP.content))

        # authors:
        i = 1
        for author in authors:
            if author.strip().startswith('#') or author.strip() == '':
                continue
            parts = author.split()

            # create author's node:
            if parts[-1].startswith('<') and parts[-1].endswith('>'):
                node = URIRef(parts[-1][1:-1])
            else:
                node = EMP.__getattr__("author" + str(i))
                i += 1

            name = Literal(' '.join(parts[0:-1]))

            self._graphs['datalad'].add((node, RDF.type, PROV.Person))
            self._graphs['datalad'].add((node, RDF.type, FOAF.Person))
            self._graphs['datalad'].add((node, FOAF.name, name))

            # the actual 'authoring' relation:
            self._graphs['datalad'].add((self._about_uri, PAV.createdBy, node))

            # same condition as above: If this is about a handle and therefore
            # a node 'EMP.content' was created, consider any author of the
            # handle also an author of its content:
            if self._about_class == 'Handle':
                self._graphs['datalad'].add((EMP.content, PAV.createdBy, node))

        # description:
        if readme is not None:
            self._graphs['datalad'].add((self._about_uri, DCTERMS.description,
                                         Literal(''.join(readme))))

        # license:
        if license_ is not None:
            if license_.__len__() == 1:
                # file contains a single line. Treat it as URI of the license:
                # TODO: How restrictive we want to be? Check for valid url?
                self._graphs['datalad'].add((self._about_uri, DCTERMS.license,
                                             URIRef(license_[0])))
            else:
                # file is assumed to contain the actual license
                self._graphs['datalad'].add((self._about_uri, DCTERMS.license,
                                             Literal(''.join(license_))))


class CustomImporter(MetadataImporter):
    # TODO: Better name
    """Importer for metadata editing

    This class somewhat bends the idea of an importer.
    Its import routine can read datalad metadata only (this is what other
    importers generate), but then allows for direct editing of the resulting
    graphs within python. This intended to be used, when "importing" or editing
    metadata by (may be interactive) datalad commands.

    Note: For any datalad metadata file, there is a separate graph. So, this is
    not the representation as a named graph!
    """
    # TODO: This needs more extensive doc, I guess. Should be done, once the
    # documentation of file layout can be referred to.

    def __init__(self, target_class, about_class=None, about_uri=None):
        super(CustomImporter, self).__init__(target_class, about_class,
                                             about_uri)

    def import_data(self, files=None, data=None):
        """import existing metadata
        """
        if files is not None:
            if not isinstance(files, list):  # single path
                if isdir(files):
                    files = listdir(files)

            for file_ in files:
                self._graphs[basename(file_).rstrip('.ttl')] = \
                    Graph().parse(file_, format="turtle")

        if data is not None:
            for key in data:
                self._graphs[basename(key).rstrip('.ttl')] = \
                    Graph().parse(data=data[key], format="turtle")

    def get_graphs(self):
        """gets the imported data

        Returns:
        --------
        dict of rdflib.Graph
        """
        return self._graphs

    def set_graphs(self, graphs):
        """sets the metadata

        Parameters:
        -----------
        graphs: dict of rdflib.Graph
            the keys are expected to be the filenames without ending as
            returned by `get_graphs`.
        """
        self._graphs = graphs