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


from os import curdir, listdir
from os.path import exists, join as opj, isfile
from .base import Interface
from ..support.param import Parameter
from ..support.constraints import EnsureStr, EnsureBool, EnsureNone
from ..support.collectionrepo import CollectionRepo
from datalad.support.collection_backends import CollectionRepoBackend
from datalad.support.collection import Collection
from datalad.support.handle import Handle
from ..support.handlerepo import HandleRepo
from datalad.support.handle_backends import HandleRepoBackend, \
    CollectionRepoHandleBackend
from ..support.metadatahandler import CustomImporter, URIRef, Literal, DLNS, \
    EMP, RDF, PAV, PROV, FOAF, DCTERMS
from ..cmdline.helpers import get_repo_instance
from ..log import lgr
from ..consts import HANDLE_META_DIR, REPO_STD_META_FILE
from datalad.cmdline.helpers import get_datalad_master

from six.moves.urllib.parse import urlparse

# PROFILE
# import line_profiler
# prof = line_profiler.LineProfiler()

class Describe(Interface):
    """Add metadata to the repository in cwd.

    Allows for adding basic metadata like author, description or license to
    a collection or handle. It's also possible to attach these metadata
    properties to different entities than just the repos, which is intended to
    be used for sub entities in the metadata. In that case the subject to be
    described has to be identified by its URI, which is used as its reference
    in the RDF data.
    This command is for use within a handle's or a collection's repository.
    It's manipulating the metadata of the repository in the current working
    directory.

    Examples:

    $ datalad describe --author "Some guy" \
            --author-email "some.guy@example.com" \
            --license MIT
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
        """
        Returns
        -------
        Handle or Collection
        """
        # PROFILE
        # prof.add_function(self.__call__)
        # prof.add_module(CollectionRepo)
        # prof.enable_by_count()

        repo = get_repo_instance()

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
                lgr.error("Subject '%s' unknown." % subject)
                raise RuntimeError("Subject '%s' unknown." % subject)
        elif isinstance(repo, HandleRepo):
            target_class = 'Handle'
            if subject in [repo.name, None]:
                about_class = 'Handle'
                about_uri = DLNS.this
                files = opj(repo.path, HANDLE_META_DIR)
            else:
                # TODO: look for internal entities as subject
                lgr.error("Subject '%s' unknown." % subject)
                raise RuntimeError("Subject '%s' unknown." % subject)
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
            repo.git_add([f for f in listdir(repo.path) if f.endswith(".ttl")])
            repo.git_commit("Metadata changed.")

        # Update metadata of local master collection:
        local_master = get_datalad_master()

        if isinstance(repo, CollectionRepo):
            # update master if it is a registered collection:
            for c in local_master.git_get_remotes():
                if repo.path == local_master.git_get_remote_url(c):
                    local_master.git_fetch(c)
        elif isinstance(repo, HandleRepo):
            # update master if it is an installed handle:

            # TODO: This takes way too long. Now, that we have new collection
            # classes, use it instead of the repo and access the handle's url
            # directly, instead of searching for it in the repo!
            # Note: Probably, we need to add an explicit connection between a
            # handle's URI and it's name in the collection level metadata.
            # The issue here is to figure out a handle's name in local master
            # from it's repository's path. This currently leads to reading the
            # metadata of all known handles to compare their paths with the one
            # we are looking for.
            for h in local_master.get_handle_list():
                handle = CollectionRepoHandleBackend(local_master, h)
                url = handle.url
                if repo.path == urlparse(url).path:
                    local_master.import_metadata_to_handle(CustomImporter,
                                                           key=h,
                                                           files=opj(
                                                              repo.path,
                                                              HANDLE_META_DIR))

        # TODO: What to do in case of a handle, if it is part of another
        # locally available collection than just the master?

        # PROFILE
        # prof.disable_by_count()
        # prof.print_stats()

        if not self.cmdline:
            if isinstance(repo, CollectionRepo):
                return CollectionRepoBackend(repo)
            elif isinstance(repo, HandleRepo):
                return HandleRepoBackend(repo)

