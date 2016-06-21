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

.. note::

   Nodes should not have side-effects, i.e. they should not modify input data,
   but yield a shallow copy if any of the field values need to be added, removed,
   or modified.  To help with creation of a new shallow copy with some fields
   adjusted, use :func:`~datalad.utils.updated`.

Pipelines
---------

A pipeline is a series of functions gathered into a list. Each function take the
output of its predecessor as its own input. The first function in the pipeline
would need to be provided with input. The simplest pipeline could look like

>>> def pipeline():
...     [
...     crawl_url('http://map.org/datasets'),
...     a_href_match(".*.mat"),
...     annex
...     ]

which crawls in a website, which is provided as input to the first function, then
matches to all files that end in `.mat`, and those files are lastly inputted to
the annex functions which simply annexes them. There can also be subpiplines within
a pipeline, which are also denoted by `[]`. Two subpipelines that exist on top of
one another, will take in the same input, but process it with different functions.
