.. -*- mode: rst -*-
.. vi: set ft=rst sts=4 ts=4 sw=4 et tw=79:

.. _chap_modref:

***********************
Python module reference
***********************

This module reference extends the manual with a comprehensive overview of the
available functionality built into datalad.  Each module in the package is
documented by a general summary of its purpose and the list of classes and
functions it provides.


High-level user interface
=========================

.. currentmodule:: datalad
.. autosummary::
   :toctree: generated

   api

Plumbing
========

.. currentmodule:: datalad
.. autosummary::
   :toctree: generated

   auto
   cmd
   consts
   log
   utils
   version
   support.annexrepo
   support.archives
   support.configparserinc
   customremotes.main
   customremotes.base
   customremotes.archives

Configuration management
========================

.. currentmodule:: datalad
.. autosummary::
   :toctree: generated

   config

Crawler
=======

.. currentmodule:: datalad
.. autosummary::
   :toctree: generated

   crawler.base
   crawler.pipeline

Test infrastructure
===================

.. currentmodule:: datalad
.. autosummary::
   :toctree: generated

   tests.utils
   tests.utils_testrepos
   tests.heavyoutput

Command line interface infrastructure
=====================================

.. currentmodule:: datalad
.. autosummary::
   :toctree: generated

   cmdline.main
   cmdline.helpers
   cmdline.common_args
