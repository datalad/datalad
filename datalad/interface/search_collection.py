# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Interface for searching a collection by its metadata
"""

__docformat__ = 'restructuredtext'


from os import curdir
from os.path import exists, join as opj
from .base import Interface
from ..support.param import Parameter
from ..support.constraints import EnsureStr, EnsureBool, EnsureNone
from ..support.collectionrepo import CollectionRepo
from ..support.collection import MetaCollection
from ..support.metadatahandler import CustomImporter, URIRef, Literal, DLNS, \
    EMP, RDF, PAV, PROV, FOAF, DCTERMS
from ..cmdline.helpers import get_repo_instance
from ..log import lgr
from appdirs import AppDirs

dirs = AppDirs("datalad", "datalad.org")


class SearchCollection(Interface):
    """search for a collection.
    """
    # TODO: A lot of doc ;)

    _params_ = dict(
        search=Parameter(
            args=('search',),
            doc="a string to search for",
            constraints=EnsureStr()))

    def __call__(self, search):

        # TODO: since search-handle and search-collection only slightly differ,
        # build a search call, that's more general and both can use
        # This one should allow for searching for other entities as well

        local_master = CollectionRepo(opj(dirs.user_data_dir,
                                      'localcollection'))

        metacollection = MetaCollection(
            [local_master.get_backend_from_branch(remote + "/master")
             for remote in local_master.git_get_remotes()] +
            [local_master.get_backend_from_branch()])

        # TODO: Bindings should be done in collection class:
        metacollection.conjunctive_graph.bind('dlns', DLNS)

        query_string = """SELECT ?g ?r {GRAPH ?g {?r rdf:type dlns:Collection .
                                             ?s ?p ?o .
                                             FILTER regex(?o, "%s")}}""" % \
                       search

        results = metacollection.conjunctive_graph.query(query_string)

        for row in results:
            print(row)
