.. _man_datalad-create-sibling-gin:

datalad create-sibling-gin
==========================

Synopsis
--------
::

  datalad create-sibling-gin [-h] [--dataset DATASET] [-r] [-R LEVELS] [-s NAME] [--existing
      {skip|error|reconfigure|replace}] [--api URL] [--credential
      NAME] [--access-protocol {https|ssh|https-ssh}]
      [--publish-depends SIBLINGNAME] [--private] [--dry-run]
      [--version] [<org-name>/]<repo-basename>

Description
-----------
Create a dataset sibling on a GIN site (with content hosting)

GIN (G-Node infrastructure) is a free data management system. It is a
GitHub-like, web-based repository store and provides fine-grained access
control to shared data. GIN is built on Git and git-annex, and can natively
host DataLad datasets, including their data content!

This command uses the main GIN instance at https://gin.g-node.org as the
default target, but other deployments can be used via the 'api'
parameter.

An SSH key, properly registered at the GIN instance, is required for data
upload via DataLad. Data download from public projects is also possible via
anonymous HTTP.

In order to be able to use this command, a personal access token has to be
generated on the platform (Account->Your Settings->Applications->Generate
New Token).

New in version 0.16

*Examples*

Create a repo 'myrepo' on GIN and register it as sibling 'mygin'::

   % datalad create-sibling-gin myrepo -s mygin

Create private repos with name(-prefix) 'myrepo' on GIN for a dataset
and all its present subdatasets::

   % datalad create-sibling-gin myrepo -r --private

Create a sibling repo on GIN, and register it as a common data source
in the dataset that is available regardless of whether the dataset was
directly cloned from GIN::

   % datalad create-sibling-gin myrepo -s gin
   # first push creates git-annex branch remotely and obtains annex UUID
   % datalad push --to gin
   % datalad siblings configure -s gin --as-common-datasrc gin-storage
   # announce availability (redo for other siblings)
   % datalad push --to gin





Options
-------
[<org-name>/]<repo-(base)name>
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
repository name, optionally including an '<organization>/' prefix if the repository shall not reside under a user's namespace. When operating recursively, a suffix will be appended to this name for each subdataset. Constraints: value must be a string

**-h**, **-\\-help**, **-\\-help-np**
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
show this help message. --help-np forcefully disables the use of a pager for displaying the help message

**-\\-dataset** *DATASET*, **-d** *DATASET*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
dataset to create the publication target for. If not given, an attempt is made to identify the dataset based on the current working directory. Constraints: Value must be a Dataset or a valid identifier of a Dataset (e.g. a path)

**-r**, **-\\-recursive**
~~~~~~~~~~~~~~~~~~~~~~~~~
if set, recurse into potential subdatasets.

**-R** LEVELS, **-\\-recursion-limit** LEVELS
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
limit recursion into subdatasets to the given number of levels. Constraints: value must be convertible to type 'int'

**-s** NAME, **-\\-name** NAME
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
name of the sibling in the local dataset installation (remote name). Constraints: value must be a string [Default: 'gin']

**-\\-existing** {skip|error|reconfigure|replace}
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
behavior when already existing or configured siblings are discovered: skip the dataset ('skip'), update the configuration ('reconfigure'), or fail ('error'). DEPRECATED DANGER ZONE: With 'replace', an existing repository will be irreversibly removed, re-initialized, and the sibling (re-)configured (thus implies 'reconfigure'). REPLACE could lead to data loss! In interactive sessions a confirmation prompt is shown, an exception is raised in non-interactive sessions. The 'replace' mode will be removed in a future release. Constraints: value must be one of ('skip', 'error', 'reconfigure', 'replace') [Default: 'error']

**-\\-api** URL
~~~~~~~~~~~~~~~
URL of the GIN instance without an 'api/<version>' suffix. Constraints: value must be a string [Default: 'https://gin.g-node.org']

**-\\-credential** NAME
~~~~~~~~~~~~~~~~~~~~~~~
name of the credential providing a personal access token to be used for authorization. The token can be supplied via configuration setting 'datalad.credential.<name>.token', or environment variable DATALAD_CREDENTIAL_<NAME>_TOKEN, or will be queried from the active credential store using the provided name. If none is provided, the host-part of the API URL is used as a name (e.g. 'https://api.github.com' -> 'api.github.com'). Constraints: value must be a string

**-\\-access-protocol** {https|ssh|https-ssh}
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
access protocol/URL to configure for the sibling. With 'https-ssh' SSH will be used for write access, whereas HTTPS is used for read access. Constraints: value must be one of ('https', 'ssh', 'https-ssh') [Default: 'https-ssh']

**-\\-publish-depends** SIBLINGNAME
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
add a dependency such that the given existing sibling is always published prior to the new sibling. This equals setting a configuration item 'remote.SIBLINGNAME.datalad-publish-depends'. This option can be given more than once to configure multiple dependencies. Constraints: value must be a string

**-\\-private**
~~~~~~~~~~~~~~~
if set, create a private repository.

**-\\-dry-run**
~~~~~~~~~~~~~~~
if set, no repository will be created, only tests for name collisions will be performed, and would-be repository names are reported for all relevant datasets.

**-\\-version**
~~~~~~~~~~~~~~~
show the module and its version which provides the command

Authors
-------
datalad is developed by The DataLad Team and Contributors <team@datalad.org>.
