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
from os.path import exists, join as opj, isfile
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
from ..consts import HANDLE_META_DIR, REPO_STD_META_FILE
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
        author_orcid=Parameter(
            args=('--author-orcid',),
            doc="ORCID URL of the author",
            constraints=EnsureStr() | EnsureNone()),
        author_email=Parameter(
            args=('--author-email',),
            doc="email address of the author",
            constraints=EnsureStr() | EnsureNone()),
        author_page=Parameter(
            args=('--author-page',),
            doc="homepage of the author",
            constraints=EnsureStr() | EnsureNone()),

        license=Parameter(
            doc="license the subject is published under.",
            constraints=EnsureStr() | EnsureNone()),
        description=Parameter(
            doc="description of the subject",
            constraints=EnsureStr() | EnsureNone()))

    def __call__(self, subject=None, author=None, author_orcid=None,
                 author_email=None, author_page=None, license=None,
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
                files = opj(repo.path, HANDLE_META_DIR)
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
        graph = importer.get_graphs()[REPO_STD_META_FILE[0:-4]]

        if about_uri not in graph.all_nodes():
            # TODO: When arbitrary entities are allowed, this has to change.
            raise RuntimeError("Didn't find URI '%s' in datalad graph." %
                               about_uri)

        # add the metadata:

        # create author node in graph;
        # choose most unique identifier available:
        a_node = None
        if author_orcid is not None:
            a_node = URIRef(author_orcid)
        elif author_email is not None:
            a_node = URIRef("mailto:" + author_email)
        elif author_page is not None:
            a_node = URIRef(author_page)
        elif author is not None:
            a_node = EMP.__getattr__("author")

        # assign author's properties:
        if a_node is not None:
            graph.add((about_uri, PAV.createdBy, a_node))
            graph.add((a_node, RDF.type, PROV.Person))
            graph.add((a_node, RDF.type, FOAF.Person))

            if author_email is not None:
                graph.add((a_node, FOAF.mbox,
                           URIRef("mailto:" + author_email)))
            if author_page is not None:
                graph.add((a_node, FOAF.homepage, URIRef(author_page)))
            if author is not None:
                graph.add((a_node, FOAF.name, Literal(author)))

        if license is not None:
            if isfile(license):
                with open(license, 'r') as f:
                    l_content = f.readlines()
                graph.add((about_uri, DCTERMS.license,
                           Literal(''.join(l_content))))
            # TODO: possible URL, dictionary of known URLs
            else:
                graph.add((about_uri, DCTERMS.license, Literal(license)))

        if description is not None:
            if isfile(description):
                with open(description, 'r') as f:
                    d_content = f.readlines()
                graph.add((about_uri, DCTERMS.description,
                           Literal(''.join(d_content))))
            else:
                graph.add((about_uri, DCTERMS.description,
                           Literal(description)))

        # save:
        importer.store_data(files)
        if isinstance(repo, HandleRepo):
            repo.add_to_git(files, "Metadata changed.")
        elif isinstance(repo, CollectionRepo):
            repo.git_add(files)
            repo.git_commit("Metadata changed.")


        # TODO: Update local collection metadata, by fetching modified collection
        # or import new metadata of the modified local handle. What to do if
        # handle is part of another collection than just the master?

        local_master = CollectionRepo(opj(dirs.user_data_dir,
                                      'localcollection'))
        # update if it is a registered collection:
        if isinstance(repo, CollectionRepo):
            for c in local_master.git_get_remotes():
                if repo.path == local_master.git_get_remote_url(c):
                    local_master.git_fetch(c)