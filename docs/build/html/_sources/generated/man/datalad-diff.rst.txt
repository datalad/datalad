.. _man_datalad-diff:

datalad diff
============

Synopsis
--------
::

  datalad diff [-h] [-f REVISION] [-t REVISION] [-d DATASET] [--annex [MODE]]
      [--untracked MODE] [-r] [-R LEVELS] [--version] [PATH ...]

Description
-----------
Report differences between two states of a dataset (hierarchy)

The two to-be-compared states are given via the --from and --to options.
These state identifiers are evaluated in the context of the (specified
or detected) dataset. In the case of a recursive report on a dataset
hierarchy, corresponding state pairs for any subdataset are determined
from the subdataset record in the respective superdataset. Only changes
recorded in a subdataset between these two states are reported, and so on.

Any paths given as additional arguments will be used to constrain the
difference report. As with Git's diff, it will not result in an error when
a path is specified that does not exist on the filesystem.

Reports are very similar to those of the STATUS command, with the
distinguished content types and states being identical.

*Examples*

Show unsaved changes in a dataset::

   % datalad diff

Compare a previous dataset state identified by shasum against current
worktree::

   % datalad diff --from <SHASUM>

Compare two branches against each other::

   % datalad diff --from branch1 --to branch2

Show unsaved changes in the dataset and potential subdatasets::

   % datalad diff -r

Show unsaved changes made to a particular file::

   % datalad diff <path/to/file>




Options
-------
PATH
~~~~
path to contrain the report to. Constraints: value must be a string

**-h**, **-\\-help**, **-\\-help-np**
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
show this help message. --help-np forcefully disables the use of a pager for displaying the help message

**-f** REVISION, **-\\-from** REVISION
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
original state to compare to, as given by any identifier that Git understands. Constraints: value must be a string [Default: 'HEAD']

**-t** REVISION, **-\\-to** REVISION
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
state to compare against the original state, as given by any identifier that Git understands. If none is specified, the state of the working tree will be compared. Constraints: value must be a string

**-d** *DATASET*, **-\\-dataset** *DATASET*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
specify the dataset to query. If no dataset is given, an attempt is made to identify the dataset based on the current working directory. Constraints: Value must be a Dataset or a valid identifier of a Dataset (e.g. a path)

**-\\-annex** [MODE]
~~~~~~~~~~~~~~~~~~~~
Switch whether to include information on the annex content of individual files in the status report, such as recorded file size. By default no annex information is reported (faster). Three report modes are available: basic information like file size and key name ('basic'); additionally test whether file content is present in the local annex ('availability'; requires one or two additional file system stat calls, but does not call git-annex), this will add the result properties 'has_content' (boolean flag) and 'objloc' (absolute path to an existing annex object file); or 'all' which will report all available information (presently identical to 'availability'). The 'basic' mode will be assumed when this option is given, but no mode is specified. Constraints: value must be one of ('basic', 'availability', 'all')

**-\\-untracked** MODE
~~~~~~~~~~~~~~~~~~~~~~
If and how untracked content is reported when comparing a revision to the state of the working tree. 'no': no untracked content is reported; 'normal': untracked files and entire untracked directories are reported as such; 'all': report individual files even in fully untracked directories. Constraints: value must be one of ('no', 'normal', 'all') [Default: 'normal']

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
