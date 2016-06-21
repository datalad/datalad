Basic principles
================

Nodes
-----

A node in a pipeline is just a callable (function of a method of a class)
which takes a dictionary, and yields a dictionary any number of times.
The simplest node could look like

>>> def add1_node(data, field='input'):
...     data_ = data.copy()
...     data_['input'] += 1
...     yield data_

which creates a simple node, intended to increment an arbitrary (specified
by `field` keyword argument) field in the input dictionary and yields
a modified dictionary as its output once.

>>> next(add1_node({'input': 1}))
{'input': 2}

.. Generators::
    Generators may be one of many things including, but not limited to: nodes,
    independent functions, or as methods of a class. Generators may yield a
    dictionary, an error message, or any number of Python variable. These
    variables may be yielded once or multiple times. A generator may also
    return as a function does, but it must yield first.

.. note::

   Nodes should not have side-effects, i.e. they should not modify input data,
   but yield a shallow copy if any of the field values need to be added, removed,
   or modified.  To help with creation of a new shallow copy with some fields
   adjusted, use :func:`~datalad.utils.updated`.

Pipelines
---------

A pipeline is a series of generators ordered into a list. Each generator takes
the output of its predecessor as its own input. The first function in the pipeline
would need to be provided with specific input. The simplest pipeline could look like

>>> def pipeline():
...     [
...     crawl_url('http://map.org/datasets'),
...     a_href_match(".*\.mat"),
...     annex
...     ]

which crawls in a website and is provided as input to the first function. `a_href_match`
then works to output all files that end in `.mat`, and those files are lastly inputted to
`annex` which simply annexes them.

.. note::
    Since pipelines depend heavily on generators, these generators must yield in order
    for an output to be produced. If a generator fails to yield, then the pipeline
    can no longer continue and it stopped at that generator.

Subpipelines
------------

A subpipline is a pipeline that lives within a greater pipeline and is also denoted by `[]`.
Two subpipelines that exist on top of one another will take in the same input, but process it
with different generators. This functionality allows for the same input to be handled in two
or more (depending on the number of subpipelines) different manners. 