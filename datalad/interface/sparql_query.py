# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""High-level interface for querying the metadata by a SPARQL query string.
"""

__docformat__ = 'restructuredtext'


from os.path import join as opj

from appdirs import AppDirs
from six import string_types

from .base import Interface
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureStr, EnsureNone, EnsureListOf
from datalad.support.collectionrepo import CollectionRepo
from datalad.support.collection import MetaCollection
from datalad.cmdline.helpers import get_datalad_master


class SPARQLQuery(Interface):
    """Query metadata by a SPARQL query string."""

    _params_ = dict(
        query=Parameter(
            doc="string containing the SPARQL query",
            constraints=EnsureStr()),
        collections=Parameter(
            args=('collections',),
            nargs='*',
            doc="collections to query; if no collection is given the query is"
                "performed on all known collections",
            constraints=EnsureListOf(string_types) | EnsureNone()))

    @staticmethod
    def __call__(query, collections=None):
        """
        Returns
        -------
        rdflib.query.QueryResult
        """

        # TODO: sanity checks for the query;

        local_master = get_datalad_master()

        be_list = list()
        if collections == [] or collections is None:
            be_list.extend([local_master.get_backend_from_branch(remote +
                                                                 "/master")
                            for remote in local_master.git_get_remotes()])
            be_list.append(local_master.get_backend_from_branch())
        else:
            for c in collections:
                if c in local_master.git_get_remotes():
                    be_list.append(local_master.get_backend_from_branch(
                        c + "/master"))
                elif c == local_master.name:
                    be_list.append(local_master.get_backend_from_branch())
                else:
                    raise RuntimeError("Collection '%s' unknown. Canceled." % c)

        m_clt = MetaCollection(be_list)

        # TODO: move following prefix bindings
        for g in m_clt.store.contexts():
            if g == m_clt.conjunctive_graph:
                # is this even possible?
                continue
            for prefix, ns in g.namespaces():
                m_clt.conjunctive_graph.bind(prefix, ns)

        # the actual query:
        results = m_clt.conjunctive_graph.query(query)

        for row in results:
            out = ""
            for col in row:
                out += "\t%s" % col
            out.lstrip('\t')
            print(out)

        return results
