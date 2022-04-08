.. _man_datalad-test:

datalad test
============

Synopsis
--------
::

  datalad test [-h] [-v] [-s] [--pdb] [-x] [--version] [module ...]

Description
-----------
Run internal DataLad (unit)tests.

This can be used to verify correct operation on the system.
It is just a thin wrapper around a call to nose, so number of
exposed options is minimal


Options
-------
module
~~~~~~
test name(s), by default all tests of DataLad core and any installed extensions are executed.

**-h**, **-\\-help**, **-\\-help-np**
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
show this help message. --help-np forcefully disables the use of a pager for displaying the help message

**-v**, **-\\-verbose**
~~~~~~~~~~~~~~~~~~~~~~~
be verbose - list test names.

**-s**, **-\\-nocapture**
~~~~~~~~~~~~~~~~~~~~~~~~~
do not capture stdout.

**-\\-pdb**
~~~~~~~~~~~
drop into debugger on failures or errors.

**-x**, **-\\-stop**
~~~~~~~~~~~~~~~~~~~~
stop running tests after the first error or failure.

**-\\-version**
~~~~~~~~~~~~~~~
show the module and its version which provides the command

Authors
-------
datalad is developed by The DataLad Team and Contributors <team@datalad.org>.
