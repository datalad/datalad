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

Dataset operations
------------------

.. currentmodule:: datalad
.. autosummary::
   :toctree: generated

   api.Dataset
   api.add
   api.create
   api.create_sibling
   api.create_sibling_github
   api.drop
   api.plugin
   api.get
   api.install
   api.publish
   api.remove
   api.save
   api.update
   api.uninstall
   api.unlock

Meta data handling
------------------

.. currentmodule:: datalad
.. autosummary::
   :toctree: generated

   api.search
   api.aggregate_metadata

Plumbing commands
-----------------

.. currentmodule:: datalad
.. autosummary::
   :toctree: generated

   api.annotate_paths
   api.clean
   api.clone
   api.create_test_dataset
   api.diff
   api.download_url
   api.ls
   api.sshrun
   api.siblings
   api.subdatasets

Miscellaneous commands
----------------------

.. currentmodule:: datalad
.. autosummary::
   :toctree: generated

   api.add_archive_content
   api.crawl
   api.crawl_init
   api.test

Plugins
-------

DataLad can be customized by plugins. The following plugins are shipped
with DataLad.

.. currentmodule:: datalad.plugin
.. autosummary::
   :toctree: generated

   add_readme
   export_tarball
   no_annex
   wtf


Support functionality
=====================

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
