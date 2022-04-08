.. _man_datalad-uninstall:

datalad uninstall
=================

Synopsis
--------
::

  datalad uninstall [-h] [-d DATASET] [-r] [--nocheck] [--if-dirty
      {fail,save-before,ignore}] [--version] [PATH ...]

Description
-----------
DEPRECATED: use the DROP command


Options
-------
PATH
~~~~
path/name of the component to be uninstalled. Constraints: value must be a string

**-h**, **-\\-help**, **-\\-help-np**
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
show this help message. --help-np forcefully disables the use of a pager for displaying the help message

**-d** DATASET, **-\\-dataset** DATASET
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
specify the dataset to perform the operation on. If no dataset is given, an attempt is made to identify a dataset based on the PATH given. Constraints: Value must be a Dataset or a valid identifier of a Dataset (e.g. a path)

**-r**, **-\\-recursive**
~~~~~~~~~~~~~~~~~~~~~~~~~
if set, recurse into potential subdatasets.

**-\\-nocheck**
~~~~~~~~~~~~~~~
whether to perform checks to assure the configured minimum number (remote) source for data. Give this option to skip checks.

**-\\-if-dirty** {fail,save-before,ignore}
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
desired behavior if a dataset with unsaved changes is discovered: 'fail' will trigger an error and further processing is aborted; 'save-before' will save all changes prior any further action; 'ignore' let's datalad proceed as if the dataset would not have unsaved changes. [Default: 'save-before']

**-\\-version**
~~~~~~~~~~~~~~~
show the module and its version which provides the command

Authors
-------
datalad is developed by The DataLad Team and Contributors <team@datalad.org>.
