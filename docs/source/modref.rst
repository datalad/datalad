.. -*- mode: rst -*-
.. vi: set ft=rst sts=4 ts=4 sw=4 et tw=79:

.. _chap_modref:

****************
Module Reference
****************

This module reference extends the manual with a comprehensive overview of the
available functionality built into datalad.  Each module in the package is
documented by a general summary of its purpose and the list of classes and
functions it provides.

.. currentmodule:: datalad

High-level user interface
=========================

.. autosummary::
   :toctree: generated

   api

Plumbing
========

.. autosummary::
   :toctree: generated

   auto
   cmd
   consts
   db
   log
   utils
   version
   support.annexrepo
   support.archives
   support.collection
   support.collectionrepo
   support.configparserinc
   customremotes.main
   customremotes.base
   customremotes.archive

Configuration management
========================

.. autosummary::
   :toctree: generated

   config.base

Crawler
=======

.. autosummary::
   :toctree: generated

   crawler.main

Test infrastructure
===================

.. autosummary::
   :toctree: generated

   tests.utils
   tests.utils_testrepos
   tests.heavyoutput

Command line interface infrastructure
=====================================

.. autosummary::
   :toctree: generated

   cmdline.main
   cmdline.helpers
   cmdline.common_args
