.. _man_datalad-clean:

datalad clean
=============

Synopsis
--------
::

  datalad clean [-h] [-d DATASET] [--what
      [{cached-archives,annex-tmp,annex-transfer,search-index} ...]]
      [--dry-run] [-r] [-R LEVELS] [--version]

Description
-----------
Clean up after DataLad (possible temporary files etc.)

Removes temporary files and directories left behind by DataLad and
git-annex in a dataset.

*Examples*

Clean all known temporary locations of a dataset::

   % datalad clean

Report on all existing temporary locations of a dataset::

   % datalad clean --dry-run

Clean all known temporary locations of a dataset and all its
subdatasets::

   % datalad clean -r

Clean only the archive extraction caches of a dataset and all its
subdatasets::

   % datalad clean --what cached-archives -r

Report on existing annex transfer files of a dataset and all its
subdatasets::

   % datalad clean --what annex-transfer -r --dry-run




Options
-------
**-h**, **-\\-help**, **-\\-help-np**
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
show this help message. --help-np forcefully disables the use of a pager for displaying the help message

**-d** *DATASET*, **-\\-dataset** *DATASET*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
specify the dataset to perform the clean operation on. If no dataset is given, an attempt is made to identify the dataset in current working directory. Constraints: Value must be a Dataset or a valid identifier of a Dataset (e.g. a path)

**-\\-what** [{cached-archives,annex-tmp,annex-transfer,search-index} ...]
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
What to clean. If none specified -- all known targets are considered.

**-\\-dry-run**
~~~~~~~~~~~~~~~
Report on cleanable locations - not actually cleaning up anything.

**-r**, **-\\-recursive**
~~~~~~~~~~~~~~~~~~~~~~~~~
if set, recurse into potential subdatasets.

**-R** LEVELS, **-\\-recursion-limit** LEVELS
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
limit recursion into subdatasets to the given number of levels. Constraints: value must be convertible to type 'int'

**-\\-version**
~~~~~~~~~~~~~~~
show the module and its version which provides the command

Authors
-------
datalad is developed by The DataLad Team and Contributors <team@datalad.org>.
