# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Interface for searching a handle by its metadata
"""

__docformat__ = 'restructuredtext'


from os import curdir
from os.path import exists, join as opj
from .base import Interface
from ..support.param import Parameter
from ..support.constraints import EnsureStr, EnsureBool, EnsureNone
from ..support.collectionrepo import CollectionRepo, \
    CollectionRepoHandleBackend
from ..support.handle import Handle
from ..support.collection import MetaCollection
from ..support.metadatahandler import CustomImporter, URIRef, Literal, DLNS, \
    EMP, RDF, PAV, PROV, FOAF, DCTERMS
from ..cmdline.helpers import get_repo_instance
from ..log import lgr
from datalad.cmdline.helpers import get_datalad_master
from six.moves.urllib.parse import urlparse


class SearchHandle(Interface):
    """Search for a handle.
    """
    # TODO: A lot of doc ;)

    _params_ = dict(
        search=Parameter(
            args=('search',),
            doc="a string to search for",
            constraints=EnsureStr()))

    def __call__(self, search):
        """
        Returns
        -------
        Handle
        """

        local_master = get_datalad_master()

        metacollection = MetaCollection(
            [local_master.get_backend_from_branch(remote + "/master")
             for remote in local_master.git_get_remotes()] +
            [local_master.get_backend_from_branch()])

        # TODO: Bindings should be done in collection class:
        metacollection.conjunctive_graph.bind('dlns', DLNS)

        query_string = """SELECT ?g ?r {GRAPH ?g {?r rdf:type dlns:Handle .
                                             ?s ?p ?o .
                                             FILTER regex(?o, "%s")}}""" % \
                       search

        results = metacollection.conjunctive_graph.query(query_string)

        rows = [row.asdict() for row in results]
        handles = list()
        locations = list()
        for row in rows:
            handles.append(str(row['g']))
            parsed_uri = urlparse(row['r'])
            if parsed_uri.scheme == 'file':
                locations.append(parsed_uri.path)
            else:
                locations.append(str(row['r']))

        if handles:
            width = max(len(h) for h in handles)
            for h, l in zip(handles, locations):
                print("%s\t%s" % (h.ljust(width), l))

            return [Handle(CollectionRepoHandleBackend(local_master, handle))
                    for handle in handles]
        else:
            return []