Workflow for supervisors and supervisees
========================================

Premise
-------

A project requires a student to work on one or more datasets. The results of
this student project are potentially interesting input into subsequent
projects, and/or some of the processing steps are common requirements for
other projects being executed at the same time.

Goal
----

Provide the student with complete data for independent work, while
simultaneously minimizing storage requirements and negative side-effects
of concurrent write access to shared storage. Create a self-contained
result that can capture the complete processing trace from input data to
results.


Implementation
--------------

Prepare a Datalad handle that contains references to all input data (handles),
and contains all code (and/or documentation) to generate all results from
the input.

Create handle
~~~~~~~~~~~~~

.. code-block:: shell

  % mkdir studentX
  studentX $ git init
  studentX $ git annex init "student project X"

Register all input data
~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: shell

  studentX % mkdir src
  studentX % git submodule add /data/supervisor/rawdataZ src/rawdata
  studentX % cd src/rawdata
  studentX/src/rawdata % git annex init
  # next lines tells git annex to hardlink files into the annex
  # if possible, but has no negative effects if not (just yields
  # a copy instead) -- potential for BIG savings
  # to get hardlinks the owner of the src data handle needs to
  # execute the get command below
  studentX/src/rawdata % git config annex.hardlink true
  # obtain all required data from the input handle
  studentX/src/rawdata % git annex get only/relevant/for/X/*.csv


Work with the handle
~~~~~~~~~~~~~~~~~~~~

A student now work with the handle. For example:

.. code-block:: shell

  studentX % mkdir code
  studentX % vim code/normalize_rawdata.sh
  studentX % bash code/normalize_rawdata.sh src/rawdata/only/relevant/for/X
  studentX % git add code/normalize_rawdata.sh
  studentX % git commit -m "Add data normalization script"
  studentX % git annex add .
  studentX % git commit -m "Generated normalized data"


Incorporate supervisor update
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

In case the supervisor make a relevant change to the input data, the student
can obtain this change, by updating the respective submodule in the project
handle. This change will be visible in the Git log and can be used to obtain
information on what parts of the processing need to be re-run.

Archiving and re-use
~~~~~~~~~~~~~~~~~~~~

By dropping the content of the referenced input data submodules the project
handle can be reduced to minimal storage requirements -- without loosing
the audit trail to the input data handles, and without and negative impact
in its own re-usability for subsequent projects.

