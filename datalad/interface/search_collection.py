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
from ..support.constraints import EnsureStr, EnsureChoice
from ..support.collectionrepo import CollectionRepo
from datalad.support.collection_backends import CollectionRepoBackend
from ..support.collection import MetaCollection, Collection
from ..support.metadatahandler import CustomImporter, URIRef, Literal, DLNS, \
    EMP, RDF, PAV, PROV, FOAF, DCTERMS
from ..cmdline.helpers import get_repo_instance
from ..log import lgr
from datalad.cmdline.helpers import get_datalad_master
from six.moves.urllib.parse import urlparse


_MODES = ('names', 'locations', 'full')

class SearchCollection(Interface):
    """Search for a collection.

    Searches for collections, based on a search string.
    If a collection's metadata contains a property of that collection, whose
    value contains the string, the collection is included in the result.
    This counts for collection level metadata only.
    It does not involve metadata of handles, contained in a collection.
    """
    # TODO: A lot of doc ;)

    _params_ = dict(
        output=Parameter(
            choices=_MODES,
            doc="""What to output as a result of search. TODO -- elaborate""",
            constraints=EnsureChoice(*_MODES)
        ),
        search=Parameter(
            args=('search',),
            doc="a string to search for",
            constraints=EnsureStr())
    )

    def __call__(self, search, output='names'):
        """
        Returns
        -------
        list of Collection
        """

        # TODO: currently returns collections uri instead of path, which may
        # lead to DLNS.this being printed put.

        # TODO: since search-handle and search-collection only slightly differ,
        # build a search call, that's more general and both can use
        # This one should allow for searching for other entities as well
        local_master = get_datalad_master()

        metacollection = MetaCollection(
            [local_master.get_backend_from_branch(remote + "/master")
             for remote in local_master.git_get_remotes()]
            # Returns local collection, which we don't want to "search for", so commented out
            # + [local_master.get_backend_from_branch()]
        )

        metacollection.update_graph_store()
        # TODO: Bindings should be done in collection class:
        metacollection.conjunctive_graph.bind('dlns', DLNS)

        # TODO: adjust query for 'full' and then implement output
        query_string = """SELECT ?g ?r {GRAPH ?g {?r rdf:type dlns:Collection .
                                             ?s ?p ?o .
                                             FILTER regex(?o, "%s")}}""" % \
                       search

        results = metacollection.conjunctive_graph.query(query_string)

        rows = [row.asdict() for row in results]
        collections = list()
        locations = list()
        for row in rows:
            collections.append(str(row['g']))
            parsed_uri = urlparse(row['r'])
            if parsed_uri.scheme == 'file':
                locations.append(parsed_uri.path)
            else:
                locations.append(str(row['r']))

        printed_collections = set()
        if collections:
            width = max(len(c) for c in collections)
            for c, l in zip(collections, locations):
                if output in {'names', 'locations'} and c in printed_collections:
                    continue
                printed_collections.add(c)
                if output == 'names':
                    out = c
                elif output == 'locations':
                    out = l
                elif output == 'full':
                    raise NotImplementedError()
                #print("%s\t%s" % (c.ljust(width), l))
                print(out)

            return [CollectionRepoBackend(local_master, col + "/master")
                    for col in collections]
        else:
            return []
