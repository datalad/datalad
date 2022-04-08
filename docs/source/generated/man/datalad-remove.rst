.. _man_datalad-remove:

datalad remove
==============

Synopsis
--------
::

  datalad remove [-h] [-d DATASET] [--drop {datasets|all}] [--reckless
      {modification|availability|undead|kill}] [-m MESSAGE] [-J NJOBS]
      [--recursive] [--nocheck] [--nosave] [--if-dirty IF_DIRTY]
      [--version] [PATH ...]

Description
-----------
Remove components from datasets

Removing "unlinks" a dataset component, such as a file or subdataset, from
a dataset. Such a removal advances the state of a dataset, just like adding
new content. A remove operation can be undone, by restoring a previous
dataset state, but might require re-obtaining file content and subdatasets
from remote locations.

This command relies on the 'drop' command for safe operation. By default,
only file content from datasets which will be uninstalled as part of
a removal will be dropped. Otherwise file content is retained, such that
restoring a previous version also immediately restores file content access,
just as it is the case for files directly committed to Git. This default
behavior can be changed to always drop content prior removal, for cases
where a minimal storage footprint for local datasets installations is
desirable.

Removing a dataset component is always a recursive operation. Removing a
directory, removes all content underneath the directory too. If
subdatasets are located under a to-be-removed path, they will be
uninstalled entirely, and all their content dropped. If any subdataset
can not be uninstalled safely, the remove operation will fail and halt.

Changed in version 0.16
   More in-depth and comprehensive safety-checks are now performed by
   default.
   The ``--if-dirty`` argument is ignored, will be removed in
   a future release, and can be removed for a safe-by-default behavior. For
   other cases consider the ``--reckless`` argument.
   The ``--save`` argument is ignored and will be removed in a future
   release, a dataset modification is now always saved. Consider save's
   ``--amend`` argument for post-remove fix-ups.
   The ``--recursive`` argument is ignored, and will be removed
   in a future release. Removal operations are always recursive, and the
   parameter can be stripped from calls for a safe-by-default behavior.

Deprecated in version 0.16
   The ``--check`` argument will be removed in a future release.
   It needs to be replaced with ``--reckless``.

*Examples*

Permanently remove a subdataset (and all further subdatasets contained
in it) from a dataset::

   % datalad remove -d <path/to/dataset> <path/to/subds>

Permanently remove a superdataset (with all subdatasets) from the
filesystem::

   % datalad remove -d <path/to/dataset>

DANGER-ZONE: Fast wipe-out a dataset and all its subdataset, bypassing
all safety checks::

   % datalad remove -d <path/to/dataset> --reckless kill




Options
-------
PATH
~~~~
path of a dataset or dataset component to be removed. Constraints: value must be a string

**-h**, **-\\-help**, **-\\-help-np**
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
show this help message. --help-np forcefully disables the use of a pager for displaying the help message

**-d** DATASET, **-\\-dataset** DATASET
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
specify the dataset to perform remove from. If no dataset is given, the current working directory is used as operation context. Constraints: Value must be a Dataset or a valid identifier of a Dataset (e.g. a path)

**-\\-drop** {datasets|all}
~~~~~~~~~~~~~~~~~~~~~~~~~~~
which dataset components to drop prior removal. This parameter is passed on to the underlying drop operation as its 'what' argument. Constraints: value must be one of ('datasets', 'all') [Default: 'datasets']

**-\\-reckless** {modification|availability|undead|kill}
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
disable individual or all data safety measures that would normally prevent potentially irreversible data-loss. With 'modification', unsaved modifications in a dataset will not be detected. This improves performance at the cost of permitting potential loss of unsaved or untracked dataset components. With 'availability', detection of dataset/branch-states that are only available in the local dataset, and detection of an insufficient number of file-content copies will be disabled. Especially the latter is a potentially expensive check which might involve numerous network transactions. With 'undead', detection of whether a to-be-removed local annex is still known to exist in the network of dataset-clones is disabled. This could cause zombie-records of invalid file availability. With 'kill', all safety-checks are disabled. Constraints: value must be one of ('modification', 'availability', 'undead', 'kill')

**-m** MESSAGE, **-\\-message** MESSAGE
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
a description of the state or the changes made to a dataset. Constraints: value must be a string

**-J** NJOBS, **-\\-jobs** NJOBS
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
how many parallel jobs (where possible) to use. "auto" corresponds to the number defined by 'datalad.runtime.max-annex-jobs' configuration item. Constraints: value must be convertible to type 'int', or value must be one of ('auto',)

**-\\-recursive**, **-r**
~~~~~~~~~~~~~~~~~~~~~~~~~
DEPRECATED and IGNORED: removal is always a recursive operation.

**-\\-nocheck**
~~~~~~~~~~~~~~~
DEPRECATED: use '--reckless availability'.

**-\\-nosave**
~~~~~~~~~~~~~~
DEPRECATED and IGNORED; use `save --amend` instead.

**-\\-if-dirty** *IF_DIRTY*
~~~~~~~~~~~~~~~~~~~~~~~~~~~
DEPRECATED and IGNORED: use --reckless instead.

**-\\-version**
~~~~~~~~~~~~~~~
show the module and its version which provides the command

Authors
-------
datalad is developed by The DataLad Team and Contributors <team@datalad.org>.
