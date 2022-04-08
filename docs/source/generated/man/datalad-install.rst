.. _man_datalad-install:

datalad install
===============

Synopsis
--------
::

  datalad install [-h] [-s SOURCE] [-d DATASET] [-g] [-D DESCRIPTION] [-r] [-R LEVELS]
      [--reckless [auto|ephemeral|shared-...]] [-J NJOBS] [--branch
      BRANCH] [--version] [PATH ...]

Description
-----------
Install a dataset from a (remote) source.

This command creates a local sibling of an existing dataset from a
(remote) location identified via a URL or path. Optional recursion into
potential subdatasets, and download of all referenced data is supported.
The new dataset can be optionally registered in an existing
superdataset by identifying it via the DATASET argument (the new
dataset's path needs to be located within the superdataset for that).

It is recommended to provide a brief description to label the dataset's
nature *and* location, e.g. "Michael's music on black laptop". This helps
humans to identify data locations in distributed scenarios.  By default an
identifier comprised of user and machine name, plus path will be generated.

When only partial dataset content shall be obtained, it is recommended to
use this command without the `get-data` flag, followed by a
`get` operation to obtain the desired data.

NOTE
  Power-user info: This command uses git clone, and
  git annex init to prepare the dataset. Registering to a
  superdataset is performed via a git submodule add operation
  in the discovered superdataset.

*Examples*

Install a dataset from Github into the current directory::

   % datalad install https://github.com/datalad-datasets/longnow-podcasts.git

Install a dataset as a subdataset into the current dataset::

   % datalad install -d . \
     --source='https://github.com/datalad-datasets/longnow-podcasts.git'

Install a dataset, and get all content right away::

   % datalad install --get-data \
     -s https://github.com/datalad-datasets/longnow-podcasts.git

Install a dataset with all its subdatasets::

   % datalad install -r \
     https://github.com/datalad-datasets/longnow-podcasts.git




Options
-------
PATH
~~~~
path/name of the installation target. If no PATH is provided a destination path will be derived from a source URL similar to git clone.

**-h**, **-\\-help**, **-\\-help-np**
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
show this help message. --help-np forcefully disables the use of a pager for displaying the help message

**-s** SOURCE, **-\\-source** SOURCE
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
URL or local path of the installation source. Constraints: value must be a string

**-d** *DATASET*, **-\\-dataset** *DATASET*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
specify the dataset to perform the install operation on. If no dataset is given, an attempt is made to identify the dataset in a parent directory of the current working directory and/or the PATH given. Constraints: Value must be a Dataset or a valid identifier of a Dataset (e.g. a path)

**-g**, **-\\-get-data**
~~~~~~~~~~~~~~~~~~~~~~~~
if given, obtain all data content too.

**-D** *DESCRIPTION*, **-\\-description** *DESCRIPTION*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
short description to use for a dataset location. Its primary purpose is to help humans to identify a dataset copy (e.g., "mike's dataset on lab server"). Note that when a dataset is published, this information becomes available on the remote side. Constraints: value must be a string

**-r**, **-\\-recursive**
~~~~~~~~~~~~~~~~~~~~~~~~~
if set, recurse into potential subdatasets.

**-R** LEVELS, **-\\-recursion-limit** LEVELS
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
limit recursion into subdatasets to the given number of levels. Constraints: value must be convertible to type 'int'

**-\\-reckless** [auto|ephemeral|shared-...]
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Obtain a dataset or subdatset and set it up in a potentially unsafe way for performance, or access reasons. Use with care, any dataset is marked as 'untrusted'. The reckless mode is stored in a dataset's local configuration under 'datalad.clone.reckless', and will be inherited to any of its subdatasets. Supported modes are: ['auto']: hard-link files between local clones. In-place modification in any clone will alter original annex content. ['ephemeral']: symlink annex to origin's annex and discard local availability info via git- annex-dead 'here'. Shares an annex between origin and clone w/o git-annex being aware of it. In case of a change in origin you need to update the clone before you're able to save new content on your end. Alternative to 'auto' when hardlinks are not an option, or number of consumed inodes needs to be minimized. Note that this mode can only be used with clones from non-bare repositories or a RIA store! Otherwise two different annex object tree structures (dirhashmixed vs dirhashlower) will be used simultaneously, and annex keys using the respective other structure will be inaccessible. ['shared-<mode>']: set up repository and annex permission to enable multi-user access. This disables the standard write protection of annex'ed files. <mode> can be any value support by 'git init --shared=', such as 'group', or 'all'. Constraints: value must be one of (True, False, 'auto', 'ephemeral'), or value must start with 'shared-'

**-J** NJOBS, **-\\-jobs** NJOBS
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
how many parallel jobs (where possible) to use. "auto" corresponds to the number defined by 'datalad.runtime.max-annex-jobs' configuration item NOTE: This option can only parallelize input retrieval (get) and output recording (save). DataLad does NOT parallelize your scripts for you. Constraints: value must be convertible to type 'int', or value must be one of ('auto',) [Default: 'auto']

**-\\-branch** *BRANCH*
~~~~~~~~~~~~~~~~~~~~~~~
Clone source at this branch or tag. This option applies only to the top-level dataset not any subdatasets that may be cloned when installing recursively. Note that if the source is a RIA URL with a version, it takes precedence over this option. Constraints: value must be a string

**-\\-version**
~~~~~~~~~~~~~~~
show the module and its version which provides the command

Authors
-------
datalad is developed by The DataLad Team and Contributors <team@datalad.org>.
