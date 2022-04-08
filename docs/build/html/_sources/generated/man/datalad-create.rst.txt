.. _man_datalad-create:

datalad create
==============

Synopsis
--------
::

  datalad create [-h] [-f] [-D DESCRIPTION] [-d DATASET] [--no-annex] [--fake-dates]
      [-c PROC] [--version] [PATH] ...

Description
-----------
Create a new dataset from scratch.

This command initializes a new dataset at a given location, or the
current directory. The new dataset can optionally be registered in an
existing superdataset (the new dataset's path needs to be located
within the superdataset for that, and the superdataset needs to be given
explicitly via --dataset). It is recommended
to provide a brief description to label the dataset's nature *and*
location, e.g. "Michael's music on black laptop". This helps humans to
identify data locations in distributed scenarios.  By default an identifier
comprised of user and machine name, plus path will be generated.

This command only creates a new dataset, it does not add existing content
to it, even if the target directory already contains additional files or
directories.

Plain Git repositories can be created via --no-annex.
However, the result will not be a full dataset, and, consequently,
not all features are supported (e.g. a description).

To create a local version of a remote dataset use the `install`
command instead.

NOTE
  Power-user info: This command uses git init and
  git annex init to prepare the new dataset. Registering to a
  superdataset is performed via a git submodule add operation
  in the discovered superdataset.

*Examples*

Create a dataset 'mydataset' in the current directory::

   % datalad create mydataset

Apply the text2git procedure upon creation of a dataset::

   % datalad create -c text2git mydataset

Create a subdataset in the root of an existing dataset::

   % datalad create -d . mysubdataset

Create a dataset in an existing, non-empty directory::

   % datalad create --force

Create a plain Git repository::

   % datalad create --no-annex mydataset




Options
-------
PATH
~~~~
path where the dataset shall be created, directories will be created as necessary. If no location is provided, a dataset will be created in the location specified by --dataset (if given) or the current working directory. Either way the command will error if the target directory is not empty. Use --force to create a dataset in a non-empty directory. Constraints: value must be a string, or Value must be a Dataset or a valid identifier of a Dataset (e.g. a path)

INIT OPTIONS
~~~~~~~~~~~~
options to pass to git init. Any argument specified after the destination path of the repository will be passed to git-init as-is. Note that not all options will lead to viable results. For example '--bare' will not yield a repository where DataLad can adjust files in its working tree.

**-h**, **-\\-help**, **-\\-help-np**
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
show this help message. --help-np forcefully disables the use of a pager for displaying the help message

**-f**, **-\\-force**
~~~~~~~~~~~~~~~~~~~~~
enforce creation of a dataset in a non-empty directory.

**-D** *DESCRIPTION*, **-\\-description** *DESCRIPTION*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
short description to use for a dataset location. Its primary purpose is to help humans to identify a dataset copy (e.g., "mike's dataset on lab server"). Note that when a dataset is published, this information becomes available on the remote side. Constraints: value must be a string

**-d** DATASET, **-\\-dataset** DATASET
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
specify the dataset to perform the create operation on. If a dataset is given along with PATH, a new subdataset will be created in it at the `path` provided to the create command. If a dataset is given but PATH is unspecified, a new dataset will be created at the location specified by this option. Constraints: Value must be a Dataset or a valid identifier of a Dataset (e.g. a path)

**-\\-no-annex**
~~~~~~~~~~~~~~~~
if set, a plain Git repository will be created without any annex.

**-\\-fake-dates**
~~~~~~~~~~~~~~~~~~
Configure the repository to use fake dates. The date for a new commit will be set to one second later than the latest commit in the repository. This can be used to anonymize dates.

**-c** PROC, **-\\-cfg-proc** PROC
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Run cfg_PROC procedure(s) (can be specified multiple times) on the created dataset. Use run-procedure --discover to get a list of available procedures, such as cfg_text2git.

**-\\-version**
~~~~~~~~~~~~~~~
show the module and its version which provides the command

Authors
-------
datalad is developed by The DataLad Team and Contributors <team@datalad.org>.
