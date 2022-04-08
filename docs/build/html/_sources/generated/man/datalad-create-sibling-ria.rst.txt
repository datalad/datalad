.. _man_datalad-create-sibling-ria:

datalad create-sibling-ria
==========================

Synopsis
--------
::

  datalad create-sibling-ria [-h] -s NAME [-d DATASET] [--storage-name NAME] [--alias ALIAS]
      [--post-update-hook] [--shared
      {false|true|umask|group|all|world|everybody|0xxx}] [--group
      GROUP] [--storage-sibling MODE] [--existing MODE]
      [--new-store-ok] [--trust-level TRUST-LEVEL] [-r] [-R LEVELS]
      [--no-storage-sibling] [--push-url
      ria+<ssh|file>://<host>[/path]] [--version]
      ria+<ssh|file|https>://<host>[/path]

Description
-----------
Creates a sibling to a dataset in a RIA store

Communication with a dataset in a RIA store is implemented via two
siblings. A regular Git remote (repository sibling) and a git-annex
special remote for data transfer (storage sibling) -- with the former
having a publication dependency on the latter. By default, the name of the
storage sibling is derived from the repository sibling's name by appending
"-storage".

The store's base path is expected to not exist, be an empty directory,
or a valid RIA store.

RIA store layout
~~~~~~~~~~~~~~~~

A RIA store is a directory tree with a dedicated subdirectory for each
dataset in the store. The subdirectory name is constructed from the
DataLad dataset ID, e.g. '124/68afe-59ec-11ea-93d7-f0d5bf7b5561', where
the first three characters of the ID are used for an intermediate
subdirectory in order to mitigate files system limitations for stores
containing a large number of datasets.

Each dataset subdirectory contains a standard bare Git repository for
the dataset.

In addition, a subdirectory 'annex' hold a standard Git-annex object
store. However, instead of using the 'dirhashlower' naming scheme for
the object directories, like Git-annex would do, a 'dirhashmixed'
layout is used -- the same as for non-bare Git repositories or regular
DataLad datasets.

Optionally, there can be a further subdirectory 'archives' with
(compressed) 7z archives of annex objects. The storage remote is able to
pull annex objects from these archives, if it cannot find in the regular
annex object store. This feature can be useful for storing large
collections of rarely changing data on systems that limit the number of
files that can be stored.

Each dataset directory also contains a 'ria-layout-version' file that
identifies the data organization (as, for example, described above).

Lastly, there is a global 'ria-layout-version' file at the store's
base path that identifies where dataset subdirectories themselves are
located. At present, this file must contain a single line stating the
version (currently "1"). This line MUST end with a newline character.

It is possible to define an alias for an individual dataset in a store by
placing a symlink to the dataset location into an 'alias/' directory
in the root of the store. This enables dataset access via URLs of format:
'ria+<protocol>://<storelocation>#~<aliasname>'.

Error logging
~~~~~~~~~~~~~

To enable error logging at the remote end, append a pipe symbol and an "l"
to the version number in ria-layout-version (like so '1|l\n').

Error logging will create files in an "error_log" directory whenever the
git-annex special remote (storage sibling) raises an exception, storing the
Python traceback of it. The logfiles are named according to the scheme
'<dataset id>.<annex uuid of the remote>.log' showing "who" ran into this
issue with which dataset. Because logging can potentially leak personal
data (like local file paths for example), it can be disabled client-side
by setting the configuration variable
"annex.ora-remote.<storage-sibling-name>.ignore-remote-config".


Options
-------
ria+<ssh|file|http(s)>://<host>[/path]
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
URL identifying the target RIA store and access protocol. If ``--push-url`` is given in addition, this is used for read access only. Otherwise it will be used for write access too and to create the repository sibling in the RIA store. Note, that HTTP(S) currently is valid for consumption only thus requiring to provide ``--push-url``. Constraints: value must be a string

**-h**, **-\\-help**, **-\\-help-np**
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
show this help message. --help-np forcefully disables the use of a pager for displaying the help message

**-s** NAME, **-\\-name** NAME
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Name of the sibling. With RECURSIVE, the same name will be used to label all the subdatasets' siblings. Constraints: value must be a string

**-d** *DATASET*, **-\\-dataset** *DATASET*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
specify the dataset to process. If no dataset is given, an attempt is made to identify the dataset based on the current working directory. Constraints: Value must be a Dataset or a valid identifier of a Dataset (e.g. a path)

**-\\-storage-name** NAME
~~~~~~~~~~~~~~~~~~~~~~~~~
Name of the storage sibling (git-annex special remote). Must not be identical to the sibling name. If not specified, defaults to the sibling name plus '-storage' suffix. If only a storage sibling is created, this setting is ignored, and the primary sibling name is used. Constraints: value must be a string

**-\\-alias** ALIAS
~~~~~~~~~~~~~~~~~~~
Alias for the dataset in the RIA store. Add the necessary symlink so that this dataset can be cloned from the RIA store using the given ALIAS instead of its ID. With `recursive=True`, only the top dataset will be aliased. Constraints: value must be a string

**-\\-post-update-hook**
~~~~~~~~~~~~~~~~~~~~~~~~
Enable git's default post-update-hook for the created sibling.

**-\\-shared** {false|true|umask|group|all|world|everybody|0xxx}
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
If given, configures the permissions in the RIA store for multi-users access. Possible values for this option are identical to those of `git init --shared` and are described in its documentation. Constraints: value must be a string, or value must be convertible to type bool

**-\\-group** GROUP
~~~~~~~~~~~~~~~~~~~
Filesystem group for the repository. Specifying the group is crucial when --shared=group. Constraints: value must be a string

**-\\-storage-sibling** MODE
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
By default, an ORA storage sibling and a Git repository sibling are created (on). Alternatively, creation of the storage sibling can be disabled (off), or a storage sibling created only and no Git sibling (only). In the latter mode, no Git installation is required on the target host. Constraints: value must be one of ('only',), or value must be convertible to type bool [Default: True]

**-\\-existing** MODE
~~~~~~~~~~~~~~~~~~~~~
Action to perform, if a (storage) sibling is already configured under the given name and/or a target already exists. In this case, a dataset can be skipped ('skip'), an existing target repository be forcefully re-initialized, and the sibling (re-)configured ('reconfigure'), or the command be instructed to fail ('error'). Constraints: value must be one of ('skip', 'error', 'reconfigure') [Default: 'error']

**-\\-new-store-ok**
~~~~~~~~~~~~~~~~~~~~
When set, a new store will be created, if necessary. Otherwise, a sibling will only be created if the url points to an existing RIA store.

**-\\-trust-level** TRUST-LEVEL
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
specify a trust level for the storage sibling. If not specified, the default git-annex trust level is used. 'trust' should be used with care (see the git- annex-trust man page). Constraints: value must be one of ('trust', 'semitrust', 'untrust')

**-r**, **-\\-recursive**
~~~~~~~~~~~~~~~~~~~~~~~~~
if set, recurse into potential subdatasets.

**-R** LEVELS, **-\\-recursion-limit** LEVELS
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
limit recursion into subdatasets to the given number of levels. Constraints: value must be convertible to type 'int'

**-\\-no-storage-sibling**
~~~~~~~~~~~~~~~~~~~~~~~~~~
This option is deprecated. Use '--storage-sibling off' instead.

**-\\-push-url** ria+<ssh|file>://<host>[/path]
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
URL identifying the target RIA store and access protocol for write access to the storage sibling. If given this will also be used for creation of the repository sibling in the RIA store. Constraints: value must be a string

**-\\-version**
~~~~~~~~~~~~~~~
show the module and its version which provides the command

Authors
-------
datalad is developed by The DataLad Team and Contributors <team@datalad.org>.
