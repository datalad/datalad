.. _man_datalad-save:

datalad save
============

Synopsis
--------
::

  datalad save [-h] [-m MESSAGE] [-d DATASET] [-t ID] [-r] [-R LEVELS] [-u] [-F
      MESSAGE_FILE] [--to-git] [-J NJOBS] [--amend] [--version] [PATH
      ...]

Description
-----------
Save the current state of a dataset

Saving the state of a dataset records changes that have been made to it.
This change record is annotated with a user-provided description.
Optionally, an additional tag, such as a version, can be assigned to the
saved state. Such tag enables straightforward retrieval of past versions at
a later point in time.

NOTE
  Before Git v2.22, any Git repository without an initial commit located
  inside a Dataset is ignored, and content underneath it will be saved to
  the respective superdataset. DataLad datasets always have an initial
  commit, hence are not affected by this behavior.

*Examples*

Save any content underneath the current directory, without
altering any potential subdataset::

   % datalad save .

Save specific content in the dataset::

   % datalad save myfile.txt

Attach a commit message to save::

   % datalad save -m 'add file' myfile.txt

Save any content underneath the current directory, and
recurse into any potential subdatasets::

   % datalad save . -r

Save any modification of known dataset content in the current
directory, but leave untracked files (e.g. temporary files) untouched::

   % datalad save -u .

Tag the most recent saved state of a dataset::

   % datalad save --version-tag 'bestyet'

Save a specific change but integrate into last commit keeping the
already recorded commit message::

   % datalad save myfile.txt --amend




Options
-------
PATH
~~~~
path/name of the dataset component to save. If given, only changes made to those components are recorded in the new state. Constraints: value must be a string

**-h**, **-\\-help**, **-\\-help-np**
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
show this help message. --help-np forcefully disables the use of a pager for displaying the help message

**-m** MESSAGE, **-\\-message** MESSAGE
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
a description of the state or the changes made to a dataset. Constraints: value must be a string

**-d** *DATASET*, **-\\-dataset** *DATASET*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
"specify the dataset to save. Constraints: Value must be a Dataset or a valid identifier of a Dataset (e.g. a path)

**-t** ID, **-\\-version-tag** ID
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
an additional marker for that state. Every dataset that is touched will receive the tag. Constraints: value must be a string

**-r**, **-\\-recursive**
~~~~~~~~~~~~~~~~~~~~~~~~~
if set, recurse into potential subdatasets.

**-R** LEVELS, **-\\-recursion-limit** LEVELS
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
limit recursion into subdatasets to the given number of levels. Constraints: value must be convertible to type 'int'

**-u**, **-\\-updated**
~~~~~~~~~~~~~~~~~~~~~~~
if given, only saves previously tracked paths.

**-F** *MESSAGE_FILE*, **-\\-message-file** *MESSAGE_FILE*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
take the commit message from this file. This flag is mutually exclusive with -m. Constraints: value must be a string

**-\\-to-git**
~~~~~~~~~~~~~~
flag whether to add data directly to Git, instead of tracking data identity only. Use with caution, there is no guarantee that a file put directly into Git like this will not be annexed in a subsequent save operation. If not specified, it will be up to git-annex to decide how a file is tracked, based on a dataset's configuration to track particular paths, file types, or file sizes with either Git or git-annex. (see https://git-annex.branchable.com/tips/largefiles).

**-J** NJOBS, **-\\-jobs** NJOBS
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
how many parallel jobs (where possible) to use. "auto" corresponds to the number defined by 'datalad.runtime.max-annex-jobs' configuration item NOTE: This option can only parallelize input retrieval (get) and output recording (save). DataLad does NOT parallelize your scripts for you. Constraints: value must be convertible to type 'int', or value must be one of ('auto',)

**-\\-amend**
~~~~~~~~~~~~~
if set, changes are not recorded in a new, separate commit, but are integrated with the changeset of the previous commit, and both together are recorded by replacing that previous commit. This is mutually exclusive with recursive operation.

**-\\-version**
~~~~~~~~~~~~~~~
show the module and its version which provides the command

Authors
-------
datalad is developed by The DataLad Team and Contributors <team@datalad.org>.
