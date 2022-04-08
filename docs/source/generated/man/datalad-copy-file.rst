.. _man_datalad-copy-file:

datalad copy-file
=================

Synopsis
--------
::

  datalad copy-file [-h] [-d DATASET] [--recursive] [--target-dir DIRECTORY] [--specs-from
      SOURCE] [-m MESSAGE] [--version] [PATH ...]

Description
-----------
Copy files and their availability metadata from one dataset to another.

The difference to a system copy command is that here additional content
availability information, such as registered URLs, is also copied to the
target dataset. Moreover, potentially required git-annex special remote
configurations are detected in a source dataset and are applied to a target
dataset in an analogous fashion. It is possible to copy a file for which no
content is available locally, by just copying the required metadata on
content identity and availability.

NOTE
  At the moment, only URLs for the special remotes 'web' (git-annex built-in)
  and 'datalad' are recognized and transferred.

The interface is modeled after the POSIX 'cp' command, but with one
additional way to specify what to copy where: --specs-from allows the
caller to flexibly input source-destination path pairs.

This command can copy files out of and into a hierarchy of nested
datasets. Unlike with other DataLad command, the --recursive switch
does not enable recursion into subdatasets, but is analogous to the
POSIX 'cp' command switch and enables subdirectory recursion,
regardless of dataset boundaries. It is not necessary to enable
recursion in order to save changes made to nested target subdatasets.

*Examples*

Copy a file into a dataset 'myds' using a path and a target directory
specification, and save its addition to 'myds'::

   % datalad copy-file path/to/myfile -d path/to/myds

Copy a file to a dataset 'myds' and save it under a new name by
providing two paths::

   % datalad copy-file path/to/myfile path/to/myds/new -d path/to/myds

Copy a file into a dataset without saving it::

   % datalad copy-file path/to/myfile -t path/to/myds

Copy a directory and its subdirectories into a dataset 'myds' and save
the addition in 'myds'::

   % datalad copy-file path/to/dir -r -d path/to/myds

Copy files using a path and optionally target specification from a
file::

   % datalad copy-file -d path/to/myds --specs-from specfile

Read a specification from stdin and pipe the output of a find command
into the copy-file command::

   % find <expr> | datalad copy-file -d path/to/myds --specs-from -




Options
-------
PATH
~~~~
paths to copy (and possibly a target path to copy to). Constraints: value must be a string

**-h**, **-\\-help**, **-\\-help-np**
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
show this help message. --help-np forcefully disables the use of a pager for displaying the help message

**-d** *DATASET*, **-\\-dataset** *DATASET*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
root dataset to save after copy operations are completed. All destination paths must be within this dataset, or its subdatasets. If no dataset is given, dataset modifications will be left unsaved. Constraints: Value must be a Dataset or a valid identifier of a Dataset (e.g. a path)

**-\\-recursive**, **-r**
~~~~~~~~~~~~~~~~~~~~~~~~~
copy directories recursively.

**-\\-target-dir** DIRECTORY, **-t** DIRECTORY
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
copy all source files into this DIRECTORY. This value is overridden by any explicit destination path provided via --specs-from. When not given, this defaults to the path of the dataset specified via --dataset. Constraints: value must be a string

**-\\-specs-from** SOURCE
~~~~~~~~~~~~~~~~~~~~~~~~~
read list of source (and destination) path names from a given file, or stdin (with '-'). Each line defines either a source path, or a source/destination path pair (separated by a null byte character).

**-m** MESSAGE, **-\\-message** MESSAGE
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
a description of the state or the changes made to a dataset. Constraints: value must be a string

**-\\-version**
~~~~~~~~~~~~~~~
show the module and its version which provides the command

Authors
-------
datalad is developed by The DataLad Team and Contributors <team@datalad.org>.
