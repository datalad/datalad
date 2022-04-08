.. _man_datalad-drop:

datalad drop
============

Synopsis
--------
::

  datalad drop [-h] [--what {filecontent|allkeys|datasets|all}] [--reckless
      {modification|availability|undead|kill}] [-d DATASET] [-r] [-R
      LEVELS] [-J NJOBS] [--nocheck] [--if-dirty IF_DIRTY] [--version]
      [PATH ...]

Description
-----------
Drop content of individual files or entire (sub)datasets

This command is the antagonist of 'get'. It can undo the retrieval of file
content, and the installation of subdatasets.

Dropping is a safe-by-default operation. Before dropping any information,
the command confirms the continued availability of file-content (see e.g.,
configuration 'annex.numcopies'), and the state of all dataset branches
from at least one known dataset sibling. Moreover, prior removal of an
entire dataset annex, that it is confirmed that it is no longer marked
as existing in the network of dataset siblings.

Importantly, all checks regarding version history availability and local
annex availability are performed using the current state of remote
siblings as known to the local dataset. This is done for performance
reasons and for resilience in case of absent network connectivity. To
ensure decision making based on up-to-date information, it is advised to
execute a dataset update before dropping dataset components.

*Examples*

Drop single file content::

   % datalad drop <path/to/file>

Drop all file content in the current dataset::

   % datalad drop

Drop all file content in a dataset and all its subdatasets::

   % datalad drop -d <path/to/dataset> -r

Disable check to ensure the configured minimum number of remote
sources for dropped data::

   % datalad drop <path/to/content> --reckless availability

Drop (uninstall) an entire dataset (will fail with subdatasets
present)::

   % datalad drop --what all

Kill a dataset recklessly with any existing subdatasets too(this will
be fast, but will disable any and all safety checks)::

   % datalad drop --what all, --reckless kill --recursive




Options
-------
PATH
~~~~
path of a dataset or dataset component to be dropped. Constraints: value must be a string

**-h**, **-\\-help**, **-\\-help-np**
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
show this help message. --help-np forcefully disables the use of a pager for displaying the help message

**-\\-what** {filecontent|allkeys|datasets|all}
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
select what type of items shall be dropped. With 'filecontent', only the file content (git-annex keys) of files in a dataset's worktree will be dropped. With 'allkeys', content of any version of any file in any branch (including, but not limited to the worktree) will be dropped. This effectively empties the annex of a local dataset. With 'datasets', only complete datasets will be dropped (implies 'allkeys' mode for each such dataset), but no filecontent will be dropped for any files in datasets that are not dropped entirely. With 'all', content for any matching file or dataset will be dropped entirely. Constraints: value must be one of ('filecontent', 'allkeys', 'datasets', 'all') [Default: 'filecontent']

**-\\-reckless** {modification|availability|undead|kill}
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
disable individual or all data safety measures that would normally prevent potentially irreversible data-loss. With 'modification', unsaved modifications in a dataset will not be detected. This improves performance at the cost of permitting potential loss of unsaved or untracked dataset components. With 'availability', detection of dataset/branch-states that are only available in the local dataset, and detection of an insufficient number of file-content copies will be disabled. Especially the latter is a potentially expensive check which might involve numerous network transactions. With 'undead', detection of whether a to-be-removed local annex is still known to exist in the network of dataset-clones is disabled. This could cause zombie-records of invalid file availability. With 'kill', all safety-checks are disabled. Constraints: value must be one of ('modification', 'availability', 'undead', 'kill')

**-d** DATASET, **-\\-dataset** DATASET
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
specify the dataset to perform drop from. If no dataset is given, the current working directory is used as operation context. Constraints: Value must be a Dataset or a valid identifier of a Dataset (e.g. a path)

**-r**, **-\\-recursive**
~~~~~~~~~~~~~~~~~~~~~~~~~
if set, recurse into potential subdatasets.

**-R** LEVELS, **-\\-recursion-limit** LEVELS
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
limit recursion into subdatasets to the given number of levels. Constraints: value must be convertible to type 'int'

**-J** NJOBS, **-\\-jobs** NJOBS
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
how many parallel jobs (where possible) to use. "auto" corresponds to the number defined by 'datalad.runtime.max-annex-jobs' configuration item. Constraints: value must be convertible to type 'int', or value must be one of ('auto',)

**-\\-nocheck**
~~~~~~~~~~~~~~~
DEPRECATED: use '--reckless availability'.

**-\\-if-dirty** *IF_DIRTY*
~~~~~~~~~~~~~~~~~~~~~~~~~~~
DEPRECATED and IGNORED: use --reckless instead.

**-\\-version**
~~~~~~~~~~~~~~~
show the module and its version which provides the command

Authors
-------
datalad is developed by The DataLad Team and Contributors <team@datalad.org>.
