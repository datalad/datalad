.. _man_datalad-create-sibling-github:

datalad create-sibling-github
=============================

Synopsis
--------
::

  datalad create-sibling-github [-h] [--dataset DATASET] [-r] [-R LEVELS] [-s NAME] [--existing
      {skip|error|reconfigure|replace}] [--github-login TOKEN]
      [--credential NAME] [--github-organization NAME]
      [--access-protocol {https|ssh|https-ssh}] [--publish-depends
      SIBLINGNAME] [--private] [--dryrun] [--dry-run] [--api URL]
      [--version] [<org-name>/]<repo-basename>

Description
-----------
Create dataset sibling on GitHub.org (or an enterprise deployment).

GitHub is a popular commercial solution for code hosting and collaborative
development. GitHub cannot host dataset content (but see LFS,
http://handbook.datalad.org/r.html?LFS). However, in combination with other
data sources and siblings, publishing a dataset to GitHub can facilitate
distribution and exchange, while still allowing any dataset consumer to
obtain actual data content from alternative sources.

In order to be able to use this command, a personal access token has to be
generated on the platform (Account->Settings->Developer Settings->Personal
access tokens->Generate new token).

Changed in version 0.16
   The API has been aligned with the some    ``create-sibling-...``
   commands of other GitHub-like    services, such as GOGS, GIN,
   GitTea.

Deprecated in version 0.16
   The ``--dryrun`` option will be removed in a future release, use
   the renamed ``--dry-run`` option instead.
   The ``--github-login`` option will be removed in a future
   release, use the ``--credential`` option instead.
   The ``--github-organization`` option will be
   removed in a future release, prefix the reposity name with ``<org>/``
   instead.

*Examples*

Use a new sibling on GIN as a common data source that is auto-
available when cloning from GitHub::

   % datalad create-sibling-gin myrepo -s gin

   # the sibling on GitHub will be used for collaborative work
   % datalad create-sibling-github myrepo -s github

   # register the storage of the public GIN repo as a data source
   % datalad siblings configure -s gin --as-common-datasrc gin-storage

   # announce its availability on github
   % datalad push --to github





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
name of the sibling in the local dataset installation (remote name). Constraints: value must be a string [Default: 'github']

**-\\-existing** {skip|error|reconfigure|replace}
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
behavior when already existing or configured siblings are discovered: skip the dataset ('skip'), update the configuration ('reconfigure'), or fail ('error'). DEPRECATED DANGER ZONE: With 'replace', an existing repository will be irreversibly removed, re-initialized, and the sibling (re-)configured (thus implies 'reconfigure'). REPLACE could lead to data loss! In interactive sessions a confirmation prompt is shown, an exception is raised in non-interactive sessions. The 'replace' mode will be removed in a future release. Constraints: value must be one of ('skip', 'error', 'reconfigure', 'replace') [Default: 'error']

**-\\-github-login** TOKEN
~~~~~~~~~~~~~~~~~~~~~~~~~~
Deprecated, use the credential parameter instead. If given must be a personal access token. Constraints: value must be a string

**-\\-credential** NAME
~~~~~~~~~~~~~~~~~~~~~~~
name of the credential providing a personal access token to be used for authorization. The token can be supplied via configuration setting 'datalad.credential.<name>.token', or environment variable DATALAD_CREDENTIAL_<NAME>_TOKEN, or will be queried from the active credential store using the provided name. If none is provided, the host-part of the API URL is used as a name (e.g. 'https://api.github.com' -> 'api.github.com'). Constraints: value must be a string

**-\\-github-organization** NAME
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Deprecated, prepend a repo name with an '<orgname>/' prefix instead. Constraints: value must be a string

**-\\-access-protocol** {https|ssh|https-ssh}
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
access protocol/URL to configure for the sibling. With 'https-ssh' SSH will be used for write access, whereas HTTPS is used for read access. Constraints: value must be one of ('https', 'ssh', 'https-ssh') [Default: 'https']

**-\\-publish-depends** SIBLINGNAME
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
add a dependency such that the given existing sibling is always published prior to the new sibling. This equals setting a configuration item 'remote.SIBLINGNAME.datalad-publish-depends'. This option can be given more than once to configure multiple dependencies. Constraints: value must be a string

**-\\-private**
~~~~~~~~~~~~~~~
if set, create a private repository.

**-\\-dryrun**
~~~~~~~~~~~~~~
Deprecated. Use the renamed ``--dry-run`` parameter.

**-\\-dry-run**
~~~~~~~~~~~~~~~
if set, no repository will be created, only tests for name collisions will be performed, and would-be repository names are reported for all relevant datasets.

**-\\-api** URL
~~~~~~~~~~~~~~~
URL of the GitHub instance API. Constraints: value must be a string [Default: 'https://api.github.com']

**-\\-version**
~~~~~~~~~~~~~~~
show the module and its version which provides the command

Authors
-------
datalad is developed by The DataLad Team and Contributors <team@datalad.org>.
