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
   api.create
   api.create_sibling
   api.create_sibling_github
   api.create_sibling_gitlab
   api.create_sibling_gogs
   api.create_sibling_gitea
   api.create_sibling_gin
   api.drop
   api.get
   api.install
   api.push
   api.remove
   api.save
   api.status
   api.update
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
   api.run_procedure


Plumbing commands
-----------------

.. currentmodule:: datalad
.. autosummary::
   :toctree: generated

   api.clean
   api.clone
   api.copy_file
   api.create_test_dataset
   api.diff
   api.download_url
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
   api.add_readme
   api.addurls
   api.check_dates
   api.configuration
   api.export_archive
   api.export_to_figshare
   api.no_annex
   api.wtf

Support functionality
=====================

.. currentmodule:: datalad
.. autosummary::
   :toctree: generated

   cmd
   consts
   log
   utils
   version
   support.gitrepo
   support.annexrepo
   support.archives
   support.extensions
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

Command interface
=================

.. currentmodule:: datalad
.. autosummary::
   :toctree: generated

   interface.base

Command line interface infrastructure
=====================================

.. currentmodule:: datalad
.. autosummary::
   :toctree: generated

   cli.exec
   cli.main
   cli.parser
   cli.renderer
