.. _man_datalad-rerun:

datalad rerun
=============

Synopsis
--------
::

  datalad rerun [-h] [--since SINCE] [-d DATASET] [-b NAME] [-m MESSAGE] [--onto base]
      [--script FILE] [--report] [--assume-ready
      {inputs|outputs|both}] [--explicit] [-J NJOBS] [--version]
      [REVISION]

Description
-----------
Re-execute previous `datalad run` commands.

This will unlock any dataset content that is on record to have
been modified by the command in the specified revision.  It will
then re-execute the command in the recorded path (if it was inside
the dataset). Afterwards, all modifications will be saved.

*Report mode*

When called with --report, this command reports information about what
would be re-executed as a series of records. There will be a record
for each revision in the specified revision range. Each of these will
have one of the following "rerun_action" values:

  - run: the revision has a recorded command that would be re-executed
  - skip-or-pick: the revision does not have a recorded command and would
    be either skipped or cherry picked
  - merge: the revision is a merge commit and a corresponding merge would
    be made

The decision to skip rather than cherry pick a revision is based on whether
the revision would be reachable from HEAD at the time of execution.

In addition, when a starting point other than HEAD is specified, there is a
rerun_action value "checkout", in which case the record includes
information about the revision the would be checked out before rerunning
any commands.

NOTE
  Currently the "onto" feature only sets the working tree of the current
  dataset to a previous state. The working trees of any subdatasets remain
  unchanged.

*Examples*

Re-execute the command from the previous commit::

   % datalad rerun

Re-execute any commands in the last five commits::

   % datalad rerun --since=HEAD~5

Do the same as above, but re-execute the commands on top of HEAD~5 in
a detached state::

   % datalad rerun --onto= --since=HEAD~5

Re-execute all previous commands and compare the old and new results::

   % # on master branch
   % datalad rerun --branch=verify --since=
   % # now on verify branch
   % datalad diff --revision=master..
   % git log --oneline --left-right --cherry-pick master...




Options
-------
REVISION
~~~~~~~~
rerun command(s) in REVISION. By default, the command from this commit will be executed, but --since can be used to construct a revision range. The default value is like "HEAD" but resolves to the main branch when on an adjusted branch. Constraints: value must be a string

**-h**, **-\\-help**, **-\\-help-np**
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
show this help message. --help-np forcefully disables the use of a pager for displaying the help message

**-\\-since** *SINCE*
~~~~~~~~~~~~~~~~~~~~~
If SINCE is a commit-ish, the commands from all commits that are reachable from `revision` but not SINCE will be re-executed (in other words, the commands in git log SINCE..REVISION). If SINCE is an empty string, it is set to the parent of the first commit that contains a recorded command (i.e., all commands in git log REVISION will be re-executed). Constraints: value must be a string

**-d** *DATASET*, **-\\-dataset** *DATASET*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
specify the dataset from which to rerun a recorded command. If no dataset is given, an attempt is made to identify the dataset based on the current working directory. If a dataset is given, the command will be executed in the root directory of this dataset. Constraints: Value must be a Dataset or a valid identifier of a Dataset (e.g. a path)

**-b** NAME, **-\\-branch** NAME
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
create and checkout this branch before rerunning the commands. Constraints: value must be a string

**-m** MESSAGE, **-\\-message** MESSAGE
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
use MESSAGE for the reran commit rather than the recorded commit message. In the case of a multi-commit rerun, all the reran commits will have this message. Constraints: value must be a string

**-\\-onto** base
~~~~~~~~~~~~~~~~~
start point for rerunning the commands. If not specified, commands are executed at HEAD. This option can be used to specify an alternative start point, which will be checked out with the branch name specified by --branch or in a detached state otherwise. As a special case, an empty value for this option means the parent of the first run commit in the specified revision list. Constraints: value must be a string

**-\\-script** FILE
~~~~~~~~~~~~~~~~~~~
extract the commands into FILE rather than rerunning. Use - to write to stdout instead. This option implies --report. Constraints: value must be a string

**-\\-report**
~~~~~~~~~~~~~~
Don't actually re-execute anything, just display what would be done. Note: If you give this option, you most likely want to set --output-format to 'json' or 'json_pp'.

**-\\-assume-ready** {inputs|outputs|both}
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Assume that inputs do not need to be retrieved and/or outputs do not need to unlocked or removed before running the command. This option allows you to avoid the expense of these preparation steps if you know that they are unnecessary. Note that this option also affects any additional outputs that are automatically inferred based on inspecting changed files in the run commit. Constraints: value must be one of ('inputs', 'outputs', 'both')

**-\\-explicit**
~~~~~~~~~~~~~~~~
Consider the specification of inputs and outputs in the run record to be explicit. Don't warn if the repository is dirty, and only save modifications to the outputs from the original record. Note that when several run commits are specified, this applies to every one. Care should also be taken when using --onto because checking out a new HEAD can easily fail when the working tree has modifications.

**-J** NJOBS, **-\\-jobs** NJOBS
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
how many parallel jobs (where possible) to use. "auto" corresponds to the number defined by 'datalad.runtime.max-annex-jobs' configuration item NOTE: This option can only parallelize input retrieval (get) and output recording (save). DataLad does NOT parallelize your scripts for you. Constraints: value must be convertible to type 'int', or value must be one of ('auto',)

**-\\-version**
~~~~~~~~~~~~~~~
show the module and its version which provides the command

Authors
-------
datalad is developed by The DataLad Team and Contributors <team@datalad.org>.
