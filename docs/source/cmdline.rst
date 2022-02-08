.. -*- mode: rst -*-
.. vi: set ft=rst sts=4 ts=4 sw=4 et tw=79:

.. _chap_cmdline:

**********************
Command line reference
**********************

Main command
============

.. toctree::
   :maxdepth: 1

   datalad: Main command entrypoint <generated/man/datalad>

Core commands
=============

A minimal set of commands that cover essential functionality. Core commands
receive special scrutiny with regard API composition and (breaking) changes.

Local operation
---------------

.. toctree::
   :maxdepth: 1

   datalad create: Create a new dataset <generated/man/datalad-create>
   datalad save: Save the state of a dataset <generated/man/datalad-save>
   datalad run: Run a shell command and record its impact on a dataset <generated/man/datalad-run>
   datalad status: Report on the state of dataset content <generated/man/datalad-status>
   datalad diff: Report differences between two states of a dataset <generated/man/datalad-diff>

Distributed operation
---------------------

.. toctree::
   :maxdepth: 1

   datalad clone: Obtain a dataset (sibling) from another location <generated/man/datalad-clone>
   datalad push: Push updates/data to a dataset sibling <generated/man/datalad-push>


Extended set of functionality
=============================

Dataset operations
------------------

.. toctree::
   :maxdepth: 1

   datalad add-readme: Add information on DataLad dataset to a README <generated/man/datalad-add-readme>
   datalad addurls: Update dataset content from a list of URLs <generated/man/datalad-addurls>
   datalad copy-file: Copy file identity and availability from one dataset to another <generated/man/datalad-copy-file>
   datalad drop: Drop datasets or dataset components <generated/man/datalad-drop>
   datalad get: Obtain any dataset content <generated/man/datalad-get>
   datalad install: Install a dataset from a (remote) source <generated/man/datalad-install>
   datalad no-annex: Configure a dataset to never put file content into an annex <generated/man/datalad-no-annex>
   datalad remove: Unlink components from a dataset <generated/man/datalad-remove>
   datalad subdatasets: Query and manipulate subdataset records of a dataset <generated/man/datalad-subdatasets>
   datalad unlock: Make dataset file content editable <generated/man/datalad-unlock>


Dataset siblings and 3rd-party platform support
-----------------------------------------------

.. toctree::
   :maxdepth: 1

   datalad siblings: Query and manipulate sibling configuration of a dataset <generated/man/datalad-siblings>
   datalad create-sibling: Create a sibling on an SSH-accessible machine <generated/man/datalad-create-sibling>
   datalad create-sibling-github: Create a sibling on GitHub <generated/man/datalad-create-sibling-github>
   datalad create-sibling-gitlab: Create a sibling on GitLab <generated/man/datalad-create-sibling-gitlab>
   datalad create-sibling-gogs: Create a sibling on GOGS <generated/man/datalad-create-sibling-gogs>
   datalad create-sibling-gitea: Create a sibling on Gitea <generated/man/datalad-create-sibling-gitea>
   datalad create-sibling-gin: Create a sibling on GIN (with content hosting) <generated/man/datalad-create-sibling-gin>
   datalad create-sibling-ria: Create a sibling in a RIA store <generated/man/datalad-create-sibling-ria>
   datalad export-archive: Export dataset content as a TAR/ZIP archive <generated/man/datalad-export-archive>
   datalad export-archive-ora: Export a local dataset annex for the ORA remote <generated/man/datalad-export-archive-ora>
   datalad export-to-figshare: Export dataset content as a ZIP archive to figshare <generated/man/datalad-export-to-figshare>
   datalad update: Obtain and incorporate updates from dataset siblings <generated/man/datalad-update>


Reproducible execution
----------------------

Extending the functionality of the core ``run`` command.

.. toctree::
   :maxdepth: 1

   datalad rerun: Re-execute previous datalad-run commands <generated/man/datalad-rerun>
   datalad run-procedure: Run prepared procedures (DataLad scripts) on a dataset <generated/man/datalad-run-procedure>


Metadata handling
-----------------

.. toctree::
   :maxdepth: 1

   datalad search: Query metadata of a dataset <generated/man/datalad-search>
   datalad metadata: Report known metadata on particular datasets or files <generated/man/datalad-metadata>
   datalad aggregate-metadata: Assemble metadata from datasets for later query <generated/man/datalad-aggregate-metadata>
   datalad extract-metadata: Run metadata extractor on a dataset or file <generated/man/datalad-extract-metadata>


Helpers and support utilities
-----------------------------

.. toctree::
   :maxdepth: 1

   datalad add-archive-content: Extract and add the content of an archive to a dataset <generated/man/datalad-add-archive-content>
   datalad clean: Remove temporary left-overs of DataLad operations <generated/man/datalad-clean>
   datalad check-dates: Scan a dataset for dates and timestamps <generated/man/datalad-check-dates>
   datalad configuration: Get and set configuration <generated/man/datalad-configuration>
   datalad create-test-dataset: Test helper <generated/man/datalad-create-test-dataset>
   datalad download-url: Download helper with support for DataLad's credential system <generated/man/datalad-download-url>
   datalad foreach-dataset: Run a command or Python code on the dataset and/or each of its sub-datasets <generated/man/datalad-foreach-dataset>
   datalad sshrun: Remote command execution using DataLad's connection management <generated/man/datalad-sshrun>
   datalad shell-completion: Helper to support command completion <generated/man/datalad-shell-completion>
   datalad test: Frontend for running DataLad's internal test battery <generated/man/datalad-test>
   datalad wtf: Report on a DataLad installation and its configuration <generated/man/datalad-wtf>


Deprecated commands
-------------------

.. toctree::
   :maxdepth: 1

   datalad uninstall: Drop subdatasets <generated/man/datalad-uninstall>
