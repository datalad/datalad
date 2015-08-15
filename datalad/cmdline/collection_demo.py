# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
""" Collections - HOWTO

This file aims to demonstrate how the classes introduced by PR #157
are intended to be used.
Currently this code will not totally work due to minor issues with the
implementation of these classes, but that's how it will look like and it should
make things clear even without currently functioning.

The functions in this file are just there to separate topics.
"""

from os.path import join as opj, expanduser, basename

from appdirs import AppDirs

from ..support.collection import Collection, MetaCollection
from ..support.collectionrepo import CollectionRepo, CollectionRepoBackend, \
    CollectionRepoHandleBackend
from ..support.handle import Handle, HandleBackend
from ..support.handlerepo import HandleRepo, HandleRepoBackend
from ..support.metadatahandler import DLNS, URIRef

dirs = AppDirs("datalad", "datalad.org")


def get_local_collection_repo():
    # often we need a representation of the local "master" collection and
    # this is how we get it:
    return CollectionRepo(opj(dirs.user_data_dir, 'localcollection'),
                          name='local')


def get_local_collection():
    return Collection(src=CollectionRepoBackend(get_local_collection_repo()))


def get_local_meta_collection():

    repo = get_local_collection_repo()

    # list of collections; tuple contains (remote) branch name and remote url:
    # todo: check what about "HEAD" (git ls-tree -r ...)
    collections = [(r + '/master', repo.repo.config_reader().get_value("remote \"%s\"" % r,
                                                       "url"))
                   for r in repo.git_get_remotes()]
    # add local repo itself:
    collections.append((None, repo.path))

    mc = list()
    for c, u in collections:
        col = Collection(src=repo.get_backend_from_branch(c))
        for (p, o) in col.meta.predicate_objects(DLNS.this):
            col.meta.add((URIRef(u), p, o))
            col.meta.remove((DLNS.this, p, o))
        mc.append(col)

    return MetaCollection(src=mc, name='localmeta')


def register_collection(url, name):
    # registering a collection with the master via its url;
    # 'name' is the name of the to be created remote.
    local_col_repo = get_local_collection_repo()
    local_col_repo.git_remote_add(name, url)
    local_col_repo.git_fetch(name)


def unregister_collection(name):
    #TODO: (pass url as an alternative?)
    local_col_repo = get_local_collection_repo()
    local_col_repo.git_remote_remove(name)


def new_collection(path, name):
    # Creating a new collection
    col_repo = CollectionRepo(path, name=name)

    # and registering it with the master:
    register_collection(path, name)

    return col_repo


def new_handle(path, name=None):
    # if name is not given, it's the name of destination:
    if name is None:
        name = basename(path)
    # Constructor of HandleRepo creates a handle repo at 'path' in case there
    # is none:
    hdl_repo = HandleRepo(path, name=name)

    # adding to local master collection:
    # (Of course this is how a handle can be added to any collection repo)
    get_local_collection_repo().add_handle(hdl_repo, name)
    return hdl_repo


def query_coll_lvl(path, query):
    # query the collection level metadata of the collection in the repo at
    # 'path', using the sparql query string 'query':
    return Collection(src=CollectionRepoBackend(path)).meta.query(query)


def query_collection(col, query):
    # query the graphs of 'col' or the collection in the repo at 'col',
    # using the sparql query string 'query':
    # (That is one named graph per each handle the collection contains and one
    # named graph for collection level meta data)
    # Note: This means either a Collection (or MetaCollection) or a path to a
    #       collection repository is expected to be given by 'col'.

    # the metadata object:
    if isinstance(col, basestring):
        # assume a path is given
        col = Collection(src=CollectionRepoBackend(path))

    # TODO: prefix bindings should be done elsewhere:
    col.conjunctive_graph.bind("dlns", DLNS)

    # the actual query:
    result = col.conjunctive_graph.query(query)

    # print it:
    for row in result:
        print "---Result:---"
        for key in row.asdict():
            print "%s:\t%s" % (key, row[key])

    return result


def install_collection(name, dst):
    # "installing" a collection means to clone the collection's repository
    # in order to have a it locally available for applying changes

    # TODO: check name/url; name may be ambigous?!
    local_col_repo = get_local_collection_repo()
    url = local_col_repo.git_get_remote_url(name)
    installed_clone = CollectionRepo(dst, url, name=name)
    register_collection(dst, name)
    return installed_clone


def install_handle(url, dst):
    # Basically, all we need is an url of a handle repo and a destination path;
    # once we got it, it's just:
    #
    handle = HandleRepo(dst, url)
    get_local_collection_repo().add_handle(handle)






#
#     # There a lot of ways to get such an url depending on what we know.
#     # It could be the result of a query (see below), we can get it via its name
#     # (including the collection it is in) from the master via the repo-classes
#     # and we can can get it via the metadata classes.
#     # For example:
#     url = master.get_handles(col_name)[handle_name]['last_seen']
#

# def query_local_collection(sparql_str):
#     # now, there are several ways to query the metadata
#     # let's query the universe for a handle authored by Michael:
#     master_repo = get_local_collection_repo()
#     universe = MetaCollection(src=master_repo.git_get_branches(),
#                                           name="KnownUniverse")
#
#     # 1. we can do this via SPARQL:
#     # Within this context, it means to look for a named graph, which states
#     # it is a handle and it's authored by Michael:
#     # (Note: Not entirely sure about the SPARQL-Syntax yet, but at least it's
#     # quite similar to that)
#     result = universe.store.query("""
#     SELECT ?g ?b {GRAPH ?g
#     {?b rdf:type dlns:Handle .
#     ?b dlns:authoredBy "Michael Hanke" .}}""")
#     # now ?g should be bind to the graph's (i.e. the handle's) name and
#     # ?b it's url;
#     # we can iterate result object to access its rows:
#     for row in result:
#         print row
#
#     # let's look only within a certain collection 'foo':
#     result = universe['foo'].store.query(sparql_str)
#     # But if this is the only query to perform, we don't need to build the
#     # graphs of the entire universe:
#     result = Collection(src=master_repo.get_backend_from_branch(
#         'foo')).store.query(sparql_str)
#
#     # or let's say we have a list of collection names and want to look only
#     # within these collections:
#     col_list = ['foo', 'bar']
#     col_to_query = MetaCollection(src=[master_repo.get_backend_from_branch(name)
#                                        for name in col_list],
#                                   name="SomeCollections")
#     result = col_to_query.store.query(sparql_str)
#
#     # But we don't need to use SPARQL, if we don't want to for some reason.
#     # We can iterate over the triples of graph within python and over the
#     # graphs within a store. Additionally there "triple-query-methods"
#     # available via rdflib:
#     from datalad.support.metadatahandler import DLNS
#     from rdflib.namespace import RDF
#     from rdflib import Literal, Graph
#     result = []
#     for graph in col_to_query.store.contexts():
#         for handle in graph.subjects(RDF.type, DLNS.Handle):
#             if (handle, DLNS.authoredBy, Literal("Michael Hanke")) in graph:
#                 result.append({'name': graph.identifier, 'url': handle})
