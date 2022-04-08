.. _man_datalad-push:

datalad push
============

Synopsis
--------
::

  datalad push [-h] [-d DATASET] [--to SIBLING] [--since SINCE] [--data
      {anything|nothing|auto|auto-if-wanted}] [-f
      {all|gitpush|checkdatapresent}] [-r] [-R LEVELS] [-J NJOBS]
      [--version] [PATH ...]

Description
-----------
Push a dataset to a known sibling.

This makes a saved state of a dataset available to a sibling or special
remote data store of a dataset. Any target sibling must already exist and
be known to the dataset.

By default, all files tracked in the last saved state (of the current
branch) will be copied to the target location. Optionally, it is
possible to limit a push to changes relative to a particular point in
the version history of a dataset (e.g. a release tag) using the
--since option in conjunction with the specification of a reference
dataset. In recursive mode subdatasets will also be evaluated, and
only those subdatasets are pushed where a change was recorded that is
reflected in the current state of the top-level reference dataset.

NOTE
  Power-user info: This command uses git push, and git
  annex copy to push a dataset. Publication targets are either configured
  remote Git repositories, or git-annex special remotes (if they support
  data upload).


Options
-------
PATH
~~~~
path to constrain a push to. If given, only data or changes for those paths are considered for a push. Constraints: value must be a string

**-h**, **-\\-help**, **-\\-help-np**
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
show this help message. --help-np forcefully disables the use of a pager for displaying the help message

**-d** *DATASET*, **-\\-dataset** *DATASET*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
specify the dataset to push. Constraints: Value must be a Dataset or a valid identifier of a Dataset (e.g. a path)

**-\\-to** SIBLING
~~~~~~~~~~~~~~~~~~
name of the target sibling. If no name is given an attempt is made to identify the target based on the dataset's configuration (i.e. a configured tracking branch, or a single sibling that is configured for push). Constraints: value must be a string

**-\\-since** *SINCE*
~~~~~~~~~~~~~~~~~~~~~
specifies commit-ish (tag, shasum, etc.) from which to look for changes to decide whether pushing is necessary. If '^' is given, the last state of the current branch at the sibling is taken as a starting point. Constraints: value must be a string

**-\\-data** {anything|nothing|auto|auto-if-wanted}
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
what to do with (annex'ed) data. 'anything' would cause transfer of all annexed content, 'nothing' would avoid call to `git annex copy` altogether. 'auto' would use 'git annex copy' with '--auto' thus transferring only data which would satisfy "wanted" or "numcopies" settings for the remote (thus "nothing" otherwise). 'auto-if-wanted' would enable '--auto' mode only if there is a "wanted" setting for the remote, and transfer 'anything' otherwise. Constraints: value must be one of ('anything', 'nothing', 'auto', 'auto-if-wanted') [Default: 'auto-if-wanted']

**-f** {all|gitpush|checkdatapresent}, **-\\-force** {all|gitpush|checkdatapresent}
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
force particular operations, possibly overruling safety protections or optimizations: use --force with git-push ('gitpush'); do not use --fast with git-annex copy ('checkdatapresent'); combine all force modes ('all'). Constraints: value must be one of ('all', 'gitpush', 'checkdatapresent')

**-r**, **-\\-recursive**
~~~~~~~~~~~~~~~~~~~~~~~~~
if set, recurse into potential subdatasets.

**-R** LEVELS, **-\\-recursion-limit** LEVELS
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
limit recursion into subdatasets to the given number of levels. Constraints: value must be convertible to type 'int'

**-J** NJOBS, **-\\-jobs** NJOBS
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
how many parallel jobs (where possible) to use. "auto" corresponds to the number defined by 'datalad.runtime.max-annex-jobs' configuration item NOTE: This option can only parallelize input retrieval (get) and output recording (save). DataLad does NOT parallelize your scripts for you. Constraints: value must be convertible to type 'int', or value must be one of ('auto',)

**-\\-version**
~~~~~~~~~~~~~~~
show the module and its version which provides the command

Authors
-------
datalad is developed by The DataLad Team and Contributors <team@datalad.org>.
