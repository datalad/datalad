.. _man_datalad-create-test-dataset:

datalad create-test-dataset
===========================

Synopsis
--------
::

  datalad create-test-dataset [-h] [--spec SPEC] [--seed SEED] [--version] path

Description
-----------
Create test (meta-)dataset.


Options
-------
path
~~~~
path/name where to create (if specified, must not exist). Constraints: value must be a string

**-h**, **-\\-help**, **-\\-help-np**
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
show this help message. --help-np forcefully disables the use of a pager for displaying the help message

**-\\-spec** *SPEC*
~~~~~~~~~~~~~~~~~~~
spec for hierarchy, defined as a min-max (min could be omitted to assume 0) defining how many (random number from min to max) of sub-datasets to generate at any given level of the hierarchy. Each level separated from each other with /. Example: 1-3/-2 would generate from 1 to 3 subdatasets at the top level, and up to two within those at the 2nd level. Constraints: value must be a string

**-\\-seed** *SEED*
~~~~~~~~~~~~~~~~~~~
seed for rng. Constraints: value must be convertible to type 'int'

**-\\-version**
~~~~~~~~~~~~~~~
show the module and its version which provides the command

Authors
-------
datalad is developed by The DataLad Team and Contributors <team@datalad.org>.
