.. -*- mode: rst -*-
.. vi: set ft=rst sts=4 ts=4 sw=4 et tw=79:

.. _chap_modref:

****************
Module Reference
****************

This module reference extends the manual with a comprehensive overview of the
currently available functionality, that is built into datalad. However, instead
of a full list including every single line of the datalad code base, this
reference limits itself to the relevant pieces of the application programming
interface (API) that are of particular interest to users of this framework.

Each module in the package is documented by a general summary of its
purpose and the list of classes and functions it provides.

Entry Point
===========

.. autosummary::
   :toctree: generated

   datalad
   
.. the rest of the modules are relative to the top-level
.. currentmodule:: datalad.interface

Basic Facilities
=================

.. autosummary::
   :toctree: generated

   add_handle
   base
   crawl
   create_collection
   create_handle
   describe
   drop
   get
   import_metadata
   install_handle
   list_collections
   list_handles
   publish_collection
   publish_handle
   pull
   push
   register_collection
   search_collection
   search_handle
   sparql_query
   test
   uninstall_handle
   unregister_collection
   update
   upgrade_handle
   whereis
