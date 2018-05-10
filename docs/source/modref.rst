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
   api.get
   api.install
   api.publish
   api.remove
   api.save
   api.update
   api.uninstall
   api.unlock

Metadata handling
-----------------

.. currentmodule:: datalad
.. autosummary::
   :toctree: generated

   api.search
   api.metadata
   api.aggregate_metadata
   api.extract_metadata


Reproducible execution
----------------------

.. currentmodule:: datalad
.. autosummary::
   :toctree: generated

   api.run
   api.rerun


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
   api.test

Plugins
-------

DataLad can be customized by plugins. The following plugins are shipped
with DataLad.

.. currentmodule:: datalad.plugin
.. autosummary::
   :toctree: generated

   add_readme
   addurls
   check_dates
   export_archive
   export_to_figshare
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
