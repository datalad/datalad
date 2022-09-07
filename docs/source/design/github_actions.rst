.. -*- mode: rst -*-
.. vi: set ft=rst sts=4 ts=4 sw=4 et tw=79:

.. _chap_design_github_action:

*************
GitHub Action
*************

.. topic:: Specification scope and status

   This specification describes a proposed interface to a DataLad GitHub Action.
   https://github.com/datalad/datalad-action provides an implementation which loosely
   followed this specification.

The purpose of the DataLad GitHub Action is to support CI testing with DataLad datasets
by making it easy to install ``datalad`` and ``get`` data from the datasets.


Example Usage
=============

Dataset installed at ``${GITHUB_WORKSPACE}/studyforrest-data-phase2``,
``get``'s all the data::

    - uses: datalad/datalad-action@master
      with:
        datasets:
          - source: https://github.com/psychoinformatics-de/studyforrest-data-phase2
          - install_get_data: true

Specify advanced options::

    - name: Download testing data
      uses: datalad/datalad-action@master
      with:
        datalad_version: ^0.15.5
        add_datalad_to_path: false
        datasets:
          - source: https://github.com/psychoinformatics-de/studyforrest-data-phase2
          - branch: develop
          - install_path: test_data
          - install_jobs: 2
          - install_get_data: false
          - recursive: true
          - recursion_limit: 2
          - get_jobs: 2
          - get_paths:
              - sub-01
              - sub-02
              - stimuli

Options
=======

``datalad_version``
-------------------

``datalad`` version to install. Defaults to the latest release.

``add_datalad_to_path``
-----------------------

Add ``datalad`` to the ``PATH`` for manual invocation in subsequent steps.

Defaults to ``true``.

``source``
----------

URL for the dataset (mandatory).

``branch``
----------

Git branch to install (optional).

``install_path``
----------------

Path to install the dataset relative to `GITHUB_WORKSPACE`.

Defaults to the repository name.

``install_jobs``
----------------

Jobs to use for ``datalad install``.

Defaults to ``auto``.

``install_get_data``
--------------------

Get all the data in the dataset by passing ``--get-data`` to ``datalad install``.

Defaults to ``false``.

``recursive``
-------------

Boolean defining whether to clone subdatasets.

Defaults to ``true``.

``recursion_limit``
-------------------

Integer defining limits to recursion.

If not defined, there is no limit.

``get_jobs``
------------

Jobs to use for ``datalad get``.

Defaults to ``auto``.


``get_paths``
-------------

A list of paths in the dataset to download with ``datalad get``.

Defaults to everything.
