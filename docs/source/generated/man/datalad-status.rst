.. _man_datalad-status:

datalad status
==============

Synopsis
--------
::

  datalad status [-h] [-d DATASET] [--annex [MODE]] [--untracked MODE] [-r] [-R LEVELS]
      [-e {no|commit|full}] [-t {raw|eval}] [--version] [PATH ...]

Description
-----------
Report on the state of dataset content.

This is an analog to `git status` that is simultaneously crippled and more
powerful. It is crippled, because it only supports a fraction of the
functionality of its counter part and only distinguishes a subset of the
states that Git knows about. But it is also more powerful as it can handle
status reports for a whole hierarchy of datasets, with the ability to
report on a subset of the content (selection of paths) across any number
of datasets in the hierarchy.

*Path conventions*

All reports are guaranteed to use absolute paths that are underneath the
given or detected reference dataset, regardless of whether query paths are
given as absolute or relative paths (with respect to the working directory,
or to the reference dataset, when such a dataset is given explicitly).
Moreover, so-called "explicit relative paths" (i.e. paths that start with
'.' or '..') are also supported, and are interpreted as relative paths with
respect to the current working directory regardless of whether a reference
dataset with specified.

When it is necessary to address a subdataset record in a superdataset
without causing a status query for the state _within_ the subdataset
itself, this can be achieved by explicitly providing a reference dataset
and the path to the root of the subdataset like so::

  datalad status --dataset . subdspath

In contrast, when the state of the subdataset within the superdataset is
not relevant, a status query for the content of the subdataset can be
obtained by adding a trailing path separator to the query path (rsync-like
syntax)::

  datalad status --dataset . subdspath/

When both aspects are relevant (the state of the subdataset content
and the state of the subdataset within the superdataset), both queries
can be combined::

  datalad status --dataset . subdspath subdspath/

When performing a recursive status query, both status aspects of subdataset
are always included in the report.


*Content types*

The following content types are distinguished:

- 'dataset' -- any top-level dataset, or any subdataset that is properly
  registered in superdataset
- 'directory' -- any directory that does not qualify for type 'dataset'
- 'file' -- any file, or any symlink that is placeholder to an annexed
  file when annex-status reporting is enabled
- 'symlink' -- any symlink that is not used as a placeholder for an annexed
  file

*Content states*

The following content states are distinguished:

- 'clean'
- 'added'
- 'modified'
- 'deleted'
- 'untracked'

*Examples*

Report on the state of a dataset::

   % datalad status

Report on the state of a dataset and all subdatasets::

   % datalad status -r

Address a subdataset record in a superdataset without causing a status
query for the state _within_ the subdataset itself::

   % datalad status -d . mysubdataset

Get a status query for the state within the subdataset without causing
a status query for the superdataset (using trailing path separator in
the query path):::

   % datalad status -d . mysubdataset/

Report on the state of a subdataset in a superdataset and on the state
within the subdataset::

   % datalad status -d . mysubdataset mysubdataset/

Report the file size of annexed content in a dataset::

   % datalad status --annex




Options
-------
PATH
~~~~
path to be evaluated. Constraints: value must be a string

**-h**, **-\\-help**, **-\\-help-np**
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
show this help message. --help-np forcefully disables the use of a pager for displaying the help message

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

**-e** {no|commit|full}, **-\\-eval-subdataset-state** {no|commit|full}
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Evaluation of subdataset state (clean vs. modified) can be expensive for deep dataset hierarchies as subdataset have to be tested recursively for uncommitted modifications. Setting this option to 'no' or 'commit' can substantially boost performance by limiting what is being tested. With 'no' no state is evaluated and subdataset result records typically do not contain a 'state' property. With 'commit' only a discrepancy of the HEAD commit shasum of a subdataset and the shasum recorded in the superdataset's record is evaluated, and the 'state' result property only reflects this aspect. With 'full' any other modification is considered too (see the 'untracked' option for further tailoring modification testing). Constraints: value must be one of ('no', 'commit', 'full') [Default: 'full']

**-t** {raw|eval}, **-\\-report-filetype** {raw|eval}
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
THIS OPTION IS IGNORED. It will be removed in a future release. Dataset component types are always reported as-is (previous 'raw' mode), unless annex- reporting is enabled with the --annex option, in which case symlinks that represent annexed files will be reported as type='file'. Constraints: value must be one of ('raw', 'eval')

**-\\-version**
~~~~~~~~~~~~~~~
show the module and its version which provides the command

Authors
-------
datalad is developed by The DataLad Team and Contributors <team@datalad.org>.
