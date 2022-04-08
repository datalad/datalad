.. _man_datalad-get:

datalad get
===========

Synopsis
--------
::

  datalad get [-h] [-s LABEL] [-d PATH] [-r] [-R LEVELS] [-n] [-D DESCRIPTION]
      [--reckless [auto|ephemeral|shared-...]] [-J NJOBS] [--version]
      [PATH ...]

Description
-----------
Get any dataset content (files/directories/subdatasets).

This command only operates on dataset content. To obtain a new independent
dataset from some source use the CLONE command.

By default this command operates recursively within a dataset, but not
across potential subdatasets, i.e. if a directory is provided, all files in
the directory are obtained. Recursion into subdatasets is supported too. If
enabled, relevant subdatasets are detected and installed in order to
fulfill a request.

Known data locations for each requested file are evaluated and data are
obtained from some available location (according to git-annex configuration
and possibly assigned remote priorities), unless a specific source is
specified.

*Getting subdatasets*

Just as DataLad supports getting file content from more than one location,
the same is supported for subdatasets, including a ranking of individual
sources for prioritization.

The following location candidates are considered. For each candidate a
cost is given in parenthesis, higher values indicate higher cost, and thus
lower priority:

- URL of any configured superdataset remote that is known to have the
  desired submodule commit, with the submodule path appended to it.
  There can be more than one candidate (cost 500).

- In case `.gitmodules` contains a relative path instead of a URL,
  the URL of any configured superdataset remote that is known to have the
  desired submodule commit, with this relative path appended to it.
  There can be more than one candidate (cost 500).

- A URL or absolute path recorded in `.gitmodules` (cost 600).

- In case `.gitmodules` contains a relative path as a URL, the absolute
  path of the superdataset, appended with this relative path (cost 900).

Additional candidate URLs can be generated based on templates specified as
configuration variables with the pattern

  `datalad.get.subdataset-source-candidate-<name>`

where NAME is an arbitrary identifier. If `name` starts with three digits
(e.g. '400myserver') these will be interpreted as a cost, and the
respective candidate will be sorted into the generated candidate list
according to this cost. If no cost is given, a default of 700 is used.

A template string assigned to such a variable can utilize the Python format
mini language and may reference a number of properties that are inferred
from the parent dataset's knowledge about the target subdataset. Properties
include any submodule property specified in the respective `.gitmodules`
record. For convenience, an existing `datalad-id` record is made available
under the shortened name ID.

Additionally, the URL of any configured remote that contains the respective
submodule commit is available as `remote-<name>` properties, where NAME
is the configured remote name.

Lastly, all candidates are sorted according to their cost (lower values
first), and duplicate URLs are stripped, while preserving the first item in the
candidate list.

NOTE
  Power-user info: This command uses git annex get to fulfill
  file handles.

*Examples*

Get a single file::

   % datalad get <path/to/file>

Get contents of a directory::

   % datalad get <path/to/dir/>

Get all contents of the current dataset and its subdatasets::

   % datalad get . -r

Get (clone) a registered subdataset, but don't retrieve data::

   % datalad get -n <path/to/subds>




Options
-------
PATH
~~~~
path/name of the requested dataset component. The component must already be known to a dataset. To add new components to a dataset use the ADD command. Constraints: value must be a string

**-h**, **-\\-help**, **-\\-help-np**
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
show this help message. --help-np forcefully disables the use of a pager for displaying the help message

**-s** LABEL, **-\\-source** LABEL
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
label of the data source to be used to fulfill requests. This can be the name of a dataset sibling or another known source. Constraints: value must be a string

**-d** PATH, **-\\-dataset** PATH
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
specify the dataset to perform the add operation on, in which case PATH arguments are interpreted as being relative to this dataset. If no dataset is given, an attempt is made to identify a dataset for each input `path`. Constraints: Value must be a Dataset or a valid identifier of a Dataset (e.g. a path)

**-r**, **-\\-recursive**
~~~~~~~~~~~~~~~~~~~~~~~~~
if set, recurse into potential subdatasets.

**-R** LEVELS, **-\\-recursion-limit** LEVELS
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
limit recursion into subdataset to the given number of levels. Alternatively, 'existing' will limit recursion to subdatasets that already existed on the filesystem at the start of processing, and prevent new subdatasets from being obtained recursively. Constraints: value must be convertible to type 'int', or value must be one of ('existing',)

**-n**, **-\\-no-data**
~~~~~~~~~~~~~~~~~~~~~~~
whether to obtain data for all file handles. If disabled, GET operations are limited to dataset handles. This option prevents data for file handles from being obtained.

**-D** *DESCRIPTION*, **-\\-description** *DESCRIPTION*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
short description to use for a dataset location. Its primary purpose is to help humans to identify a dataset copy (e.g., "mike's dataset on lab server"). Note that when a dataset is published, this information becomes available on the remote side. Constraints: value must be a string

**-\\-reckless** [auto|ephemeral|shared-...]
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Obtain a dataset or subdatset and set it up in a potentially unsafe way for performance, or access reasons. Use with care, any dataset is marked as 'untrusted'. The reckless mode is stored in a dataset's local configuration under 'datalad.clone.reckless', and will be inherited to any of its subdatasets. Supported modes are: ['auto']: hard-link files between local clones. In-place modification in any clone will alter original annex content. ['ephemeral']: symlink annex to origin's annex and discard local availability info via git- annex-dead 'here'. Shares an annex between origin and clone w/o git-annex being aware of it. In case of a change in origin you need to update the clone before you're able to save new content on your end. Alternative to 'auto' when hardlinks are not an option, or number of consumed inodes needs to be minimized. Note that this mode can only be used with clones from non-bare repositories or a RIA store! Otherwise two different annex object tree structures (dirhashmixed vs dirhashlower) will be used simultaneously, and annex keys using the respective other structure will be inaccessible. ['shared-<mode>']: set up repository and annex permission to enable multi-user access. This disables the standard write protection of annex'ed files. <mode> can be any value support by 'git init --shared=', such as 'group', or 'all'. Constraints: value must be one of (True, False, 'auto', 'ephemeral'), or value must start with 'shared-'

**-J** NJOBS, **-\\-jobs** NJOBS
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
how many parallel jobs (where possible) to use. "auto" corresponds to the number defined by 'datalad.runtime.max-annex-jobs' configuration item NOTE: This option can only parallelize input retrieval (get) and output recording (save). DataLad does NOT parallelize your scripts for you. Constraints: value must be convertible to type 'int', or value must be one of ('auto',) [Default: 'auto']

**-\\-version**
~~~~~~~~~~~~~~~
show the module and its version which provides the command

Authors
-------
datalad is developed by The DataLad Team and Contributors <team@datalad.org>.
