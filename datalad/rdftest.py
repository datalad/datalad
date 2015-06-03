import datalad.support.collectionrepo as clt
import datalad.support.handlerepo as hdl

from rdflib import Namespace, Literal, Graph, ConjunctiveGraph, URIRef, BNode
from rdflib.namespace import RDF, RDFS, FOAF
from rdflib.plugins.memory import IOMemory
import rdflib
import time
DLNS = Namespace('http://www.datalad.org/terms/')


store_1 = IOMemory()
store_1.bind('dlns', DLNS)


graph_1 = Graph(store=store_1, identifier='SomeHandle')
graph_1.bind('dlns', DLNS)
handle_node = URIRef('path/to/SomeHandle')
graph_1.add((handle_node, RDF.type, DLNS.Handle))
author_node = BNode("Myself")
graph_1.add((handle_node, DLNS.authoredBy, author_node))
graph_1.add((author_node, DLNS.homepage, URIRef('http://www.mypage.de')))
graph_1.add((author_node, DLNS.name, Literal("Benjamin Poldrack")))


graph_2 = Graph(store=store_1, identifier='AnotherHandle')
graph_2.bind('dlns', DLNS)
handle_node = URIRef('path/to/another/Handle')
graph_2.add((handle_node, RDF.type, DLNS.Handle))
author_node = BNode("Yarik")
graph_2.add((handle_node, DLNS.authoredBy, author_node))
graph_2.add((author_node, DLNS.homepage, URIRef('http://http://www.onerussian.com/')))
graph_2.add((author_node, DLNS.name, Literal("Yaroslav Halchenko")))

ANS = Namespace('http://www.anothernamespace.org/ontology/#')
graph_3 = Graph(store=store_1, identifier='NotAHandle')
graph_3.bind('ans', ANS)
graph_3.add((URIRef('path/to/something/else'), RDF.type, ANS.somethingelse))
graph_3.add((URIRef('path/to/something/else'), DLNS.authoredBy, author_node))
graph_3.add((author_node, DLNS.homepage, URIRef('http://http://www.onerussian.com/')))
graph_3.add((author_node, DLNS.name, Literal("Yaroslav Halchenko")))

con_graph = ConjunctiveGraph(store=store_1)

print "querying for known handles ..."
start = time.time()
result = con_graph.query("""
SELECT ?g ?b {GRAPH ?g {
    ?b rdf:type dlns:Handle}}""")
end = time.time() - start
print "Time: %s" % end
for row in result:
    print row


print "querying for known handles ..."
start = time.time()
result = con_graph.query("""
SELECT ?g ?b {GRAPH ?g {
        ?b rdf:type dlns:Handle}}""")
end = time.time() - start
print "Time: %s" % end
for row in result:
    print row

print "querying for handles authored by Yarik ..."
start = time.time()
result = con_graph.query("""
SELECT ?g {GRAPH ?g {
        ?b rdf:type dlns:Handle .
        ?b dlns:authoredBy ?x .
        ?x dlns:name "Yaroslav Halchenko" .}}""")
end = time.time() - start
print "Time: %s" % end
for row in result:
    print row

print "querying for something authored by Yarik ..."
start = time.time()
result = con_graph.query("""
SELECT ?g {GRAPH ?g {
        ?b dlns:authoredBy ?x .
        ?x dlns:name "Yaroslav Halchenko" .}}""")
end = time.time() - start
print "Time: %s" % end
for row in result:
    print row