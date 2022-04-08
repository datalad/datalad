.. _man_datalad-subdatasets:

datalad subdatasets
===================

Synopsis
--------
::

  datalad subdatasets [-h] [-d DATASET] [--state {present|absent|any}] [--fulfilled
      FULFILLED] [-r] [-R LEVELS] [--contains PATH] [--bottomup]
      [--set-property NAME VALUE] [--delete-property NAME] [--version]
      [PATH ...]

Description
-----------
Report subdatasets and their properties.

The following properties are reported (if possible) for each matching
subdataset record.

"name"
    Name of the subdataset in the parent (often identical with the
    relative path in the parent dataset)

"path"
    Absolute path to the subdataset

"parentds"
    Absolute path to the parent dataset

"gitshasum"
    SHA1 of the subdataset commit recorded in the parent dataset

"state"
    Condition of the subdataset: 'absent', 'present'

"gitmodule_url"
    URL of the subdataset recorded in the parent

"gitmodule_name"
    Name of the subdataset recorded in the parent

"gitmodule_<label>"
    Any additional configuration property on record.

Performance note: Property modification, requesting BOTTOMUP reporting
order, or a particular numerical `recursion_limit` implies an internal
switch to an alternative query implementation for recursive query that is
more flexible, but also notably slower (performs one call to Git per
dataset versus a single call for all combined).

The following properties for subdatasets are recognized by DataLad
(without the 'gitmodule\_' prefix that is used in the query results):

"datalad-recursiveinstall"
    If set to 'skip', the respective subdataset is skipped when DataLad
    is recursively installing its superdataset. However, the subdataset
    remains installable when explicitly requested, and no other features
    are impaired.

"datalad-url"
    If a subdataset was originally established by cloning, 'datalad-url'
    records the URL that was used to do so. This might be different from
    'url' if the URL contains datalad specific pieces like any URL of the
    form "ria+<some protocol>...".


Options
-------
PATH
~~~~
path/name to query for subdatasets. Defaults to the current directory. Constraints: value must be a string

**-h**, **-\\-help**, **-\\-help-np**
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
show this help message. --help-np forcefully disables the use of a pager for displaying the help message

**-d** *DATASET*, **-\\-dataset** *DATASET*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
specify the dataset to query. If no dataset is given, an attempt is made to identify the dataset based on the input and/or the current working directory. Constraints: Value must be a Dataset or a valid identifier of a Dataset (e.g. a path)

**-\\-state** {present|absent|any}
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
indicate which (sub)datasets to consider: either only locally present, absent, or any of those two kinds. Constraints: value must be one of ('present', 'absent', 'any') [Default: 'any']

**-\\-fulfilled** *FULFILLED*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
DEPRECATED: use --state instead. If given, must be a boolean flag indicating whether to consider either only locally present or absent datasets. By default all subdatasets are considered regardless of their status. Constraints: value must be convertible to type bool [Default: None(DEPRECATED)]

**-r**, **-\\-recursive**
~~~~~~~~~~~~~~~~~~~~~~~~~
if set, recurse into potential subdatasets.

**-R** LEVELS, **-\\-recursion-limit** LEVELS
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
limit recursion into subdatasets to the given number of levels. Constraints: value must be convertible to type 'int'

**-\\-contains** PATH
~~~~~~~~~~~~~~~~~~~~~
limit to the subdatasets containing the given path. If a root path of a subdataset is given, the last considered dataset will be the subdataset itself. This option can be given multiple times, in which case datasets that contain any of the given paths will be considered. Constraints: value must be a string

**-\\-bottomup**
~~~~~~~~~~~~~~~~
whether to report subdatasets in bottom-up order along each branch in the dataset tree, and not top-down.

**-\\-set-property** NAME VALUE
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Name and value of one or more subdataset properties to be set in the parent dataset's .gitmodules file. The property name is case-insensitive, must start with a letter, and consist only of alphanumeric characters. The value can be a Python format() template string wrapped in '<>' (e.g. '<{gitmodule_name}>'). Supported keywords are any item reported in the result properties of this command, plus 'refds_relpath' and 'refds_relname': the relative path of a subdataset with respect to the base dataset of the command call, and, in the latter case, the same string with all directory separators replaced by dashes. This option can be given multiple times. Constraints: value must be a string

**-\\-delete-property** NAME
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Name of one or more subdataset properties to be removed from the parent dataset's .gitmodules file. This option can be given multiple times. Constraints: value must be a string

**-\\-version**
~~~~~~~~~~~~~~~
show the module and its version which provides the command

Authors
-------
datalad is developed by The DataLad Team and Contributors <team@datalad.org>.
