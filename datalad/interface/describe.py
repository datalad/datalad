# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Interface for adding metadata
"""

__docformat__ = 'restructuredtext'


from os import curdir
from os.path import exists, join as opj
from .base import Interface
from ..support.param import Parameter
from ..support.constraints import EnsureStr, EnsureBool, EnsureNone
from ..support.collectionrepo import CollectionRepo, CollectionRepoBackend, \
    CollectionRepoHandleBackend
from ..support.handlerepo import HandleRepo
from ..support.metadatahandler import CustomImporter, URIRef, Literal, DLNS, \
    EMP, RDF, PAV, PROV, FOAF, DCTERMS
from ..cmdline.helpers import get_repo_instance
from ..log import lgr
from appdirs import AppDirs

dirs = AppDirs("datalad", "datalad.org")


class Describe(Interface):
    """Add metadata to the repository in cwd.
    """
    # TODO: A lot of doc ;)

    _params_ = dict(
        subject=Parameter(
            args=('subject',),
            doc="subject to describe. By default it's the repository we "
                "are in.",
            nargs='?',
            constraints=EnsureStr() | EnsureNone()),
        author=Parameter(
            doc="name of the author of the subject",
            constraints=EnsureStr() | EnsureNone()),
        license=Parameter(
            doc="license the subject is published under.",
            constraints=EnsureStr() | EnsureNone()),
        description=Parameter(
            doc="description of the subject",
            constraints=EnsureStr() | EnsureNone()))

    def __call__(self, subject=None, author=None, license_=None,
                 description=None):
        repo = get_repo_instance()

        # TODO: use path constants!
        if isinstance(repo, CollectionRepo):
            target_class = 'Collection'
            if subject in [repo.name, None]:
                about_class = 'Collection'
                about_uri = DLNS.this
                files = repo.path
            elif subject in repo.get_handle_list():
                about_class = 'Handle'
                about_uri = URIRef(CollectionRepoHandleBackend(repo,
                                                               subject).url)
                files = opj(repo.path, repo._key2filename(subject))
            else:
                # TODO: look for internal entities as subject
                lgr.error("Subject '%s' unknwon." % subject)
                raise RuntimeError("Subject '%s' unknwon." % subject)
        elif isinstance(repo, HandleRepo):
            target_class = 'Handle'
            if subject in [repo.name, None]:
                about_class = 'Handle'
                about_uri = DLNS.this
                files = opj(repo.path, '.datalad')
            else:
                # TODO: look for internal entities as subject
                lgr.error("Subject '%s' unknwon." % subject)
                raise RuntimeError("Subject '%s' unknwon." % subject)
        else:
            lgr.error("Don't know how to handle object of class %s" %
                      repo.__class__)
            raise RuntimeError("Don't know how to handle object of class %s" %
                               repo.__class__)

        importer = CustomImporter(target_class=target_class,
                                  about_class=about_class,
                                  about_uri=about_uri)
        # read existing metadata:
        importer.import_data(files)
        graphs = importer.get_graphs()

        if about_uri not in graphs['datalad'].all_nodes():
            # TODO: When arbitrary entities are allowed, this has to change.
            raise RuntimeError("Didn't find URI '%s' in datalad graph.")

        # TODO: Remove the following DEBUG Output:
        lgr.error("Files: %s" % files)
        lgr.error("Graph:\n%s\n\nAbout URI: %s" %
                  (graphs['datalad'].serialize(format="turtle"), about_uri))

        # add the metadata:
        # TODO: this is just basic. Will get more complex by adding way more
        # options to this command

        if author is not None:
            a_node = EMP.__getattr__("author")
            graphs['datalad'].add((about_uri, PAV.createdBy, a_node))
            graphs['datalad'].add((a_node, RDF.type, PROV.Person))
            graphs['datalad'].add((a_node, RDF.type, FOAF.Person))
            graphs['datalad'].add((a_node, FOAF.name, Literal(author)))

        # TODO: check what is given by license_ and
        # description: File, Text, URL, ...?
        if license_ is not None:
            graphs['datalad'].add((about_uri, DCTERMS.license,
                                   URIRef(license_)))

        if description is not None:
            graphs['datalad'].add((about_uri, DCTERMS.description,
                                   Literal(description)))

        # save:
        importer.set_graphs(graphs)
        importer.store_data(files)
