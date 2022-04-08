.. _man_datalad-foreach-dataset:

datalad foreach-dataset
=======================

Synopsis
--------
::

  datalad foreach-dataset [-h] [--cmd-type {auto|external|exec|eval}] [-d DATASET] [--state
      {present|absent|any}] [-r] [-R LEVELS] [--contains PATH]
      [--bottomup] [-s] [--output-streams {capture|pass-through}]
      [--chpwd {ds|pwd}] [--safe-to-consume
      {auto|all-subds-done|superds-done|always}] [-J NJOBS]
      [--version] ...

Description
-----------
Run a command or Python code on the dataset and/or each of its sub-datasets.

This command provides a convenience for the cases were no dedicated DataLad command
is provided to operate across the hierarchy of datasets. It is very similar to
`git submodule foreach` command with the following major differences

- by default (unless --subdatasets-only) it would
  include operation on the original dataset as well,
- subdatasets could be traversed in bottom-up order,
- can execute commands in parallel (see JOBS option), but would account for the order,
  e.g. in bottom-up order command is executed in super-dataset only after it is executed
  in all subdatasets.

Additional notes:

- for execution of "external" commands we use the environment used to execute external
  git and git-annex commands.

*Command format*

--cmd-type external: A few placeholders are supported in the command
via Python format specification:


- "{pwd}" will be replaced with the full path of the current working directory.
- "{ds}" and "{refds}" will provide instances of the dataset currently
  operated on and the reference "context" dataset which was provided via ``dataset``
  argument.
- "{tmpdir}" will be replaced with the full path of a temporary directory.

*Examples*

Aggressively  git clean  all datasets, running 5 parallel jobs::

   % datalad foreach-dataset -r -J 5 git clean -dfx




Options
-------
COMMAND
~~~~~~~
command for execution. A leading '--' can be used to disambiguate this command from the preceding options to DataLad. For --cmd-type exec or eval only a single command argument (Python code) is supported.

**-h**, **-\\-help**, **-\\-help-np**
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
show this help message. --help-np forcefully disables the use of a pager for displaying the help message

**-\\-cmd-type** {auto|external|exec|eval}
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
type of the command. EXTERNAL: to be run in a child process using dataset's runner; 'exec': Python source code to execute using 'exec(), no value returned; 'eval': Python source code to evaluate using 'eval()', return value is placed into 'result' field. 'auto': If used via Python API, and `cmd` is a Python function, it will use 'eval', and otherwise would assume 'external'. Constraints: value must be one of ('auto', 'external', 'exec', 'eval') [Default: 'auto']

**-d** *DATASET*, **-\\-dataset** *DATASET*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
specify the dataset to operate on. If no dataset is given, an attempt is made to identify the dataset based on the input and/or the current working directory. Constraints: Value must be a Dataset or a valid identifier of a Dataset (e.g. a path)

**-\\-state** {present|absent|any}
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
indicate which (sub)datasets to consider: either only locally present, absent, or any of those two kinds. Constraints: value must be one of ('present', 'absent', 'any') [Default: 'present']

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

**-s**, **-\\-subdatasets-only**
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
whether to exclude top level dataset. It is implied if a non-empty CONTAINS is used.

**-\\-output-streams** {capture|pass-through}, **-\\-o-s** {capture|pass-through}
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
whether to capture and return outputs from 'cmd' in the record ('stdout', 'stderr') or just 'pass-through' to the screen (and thus absent from returned record). Constraints: value must be one of ('capture', 'pass-through') [Default: 'pass-through']

**-\\-chpwd** {ds|pwd}
~~~~~~~~~~~~~~~~~~~~~~
'ds' will change working directory to the top of the corresponding dataset. With 'pwd' no change of working directory will happen. Note that for Python commands, due to use of threads, we do not allow chdir=ds to be used with jobs > 1. Hint: use 'ds' and 'refds' objects' methods to execute commands in the context of those datasets. Constraints: value must be one of ('ds', 'pwd') [Default: 'ds']

**-\\-safe-to-consume** {auto|all-subds-done|superds-done|always}
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Important only in the case of parallel (jobs greater than 1) execution. 'all- subds-done' instructs to not consider superdataset until command finished execution in all subdatasets (it is the value in case of 'auto' if traversal is bottomup). 'superds-done' instructs to not process subdatasets until command finished in the super-dataset (it is the value in case of 'auto' in traversal is not bottom up, which is the default). With 'always' there is no constraint on either to execute in sub or super dataset. Constraints: value must be one of ('auto', 'all-subds-done', 'superds-done', 'always') [Default: 'auto']

**-J** NJOBS, **-\\-jobs** NJOBS
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
how many parallel jobs (where possible) to use. "auto" corresponds to the number defined by 'datalad.runtime.max-annex-jobs' configuration item NOTE: This option can only parallelize input retrieval (get) and output recording (save). DataLad does NOT parallelize your scripts for you. Constraints: value must be convertible to type 'int', or value must be one of ('auto',)

**-\\-version**
~~~~~~~~~~~~~~~
show the module and its version which provides the command

Authors
-------
datalad is developed by The DataLad Team and Contributors <team@datalad.org>.
