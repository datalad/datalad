.. _man_datalad-create-sibling-gitlab:

datalad create-sibling-gitlab
=============================

Synopsis
--------
::

  datalad create-sibling-gitlab [-h] [--site SITENAME] [--project NAME/LOCATION] [--layout
      {hierarchy|collection|flat}] [--dataset DATASET] [-r] [-R
      LEVELS] [-s NAME] [--existing {skip|error|reconfigure}]
      [--access {http|ssh|ssh+http}] [--publish-depends SIBLINGNAME]
      [--description DESCRIPTION] [--dryrun] [--dry-run] [--version]
      [PATH ...]

Description
-----------
Create dataset sibling at a GitLab site

An existing GitLab project, or a project created via the GitLab web
interface can be configured as a sibling with the siblings
command. Alternatively, this command can create a GitLab project at any
location/path a given user has appropriate permissions for. This is
particularly helpful for recursive sibling creation for subdatasets. API
access and authentication are implemented via python-gitlab, and all its
features are supported. A particular GitLab site must be configured in a
named section of a python-gitlab.cfg file (see
https://python-gitlab.readthedocs.io/en/stable/cli.html#configuration for
details), such as::

  [mygit]
  url = https://git.example.com
  api_version = 4
  private_token = abcdefghijklmnopqrst

Subsequently, this site is identified by its name ('mygit' in the example
above).

(Recursive) sibling creation for all, or a selected subset of subdatasets
is supported with three different project layouts (see --layout):

"hierarchy"
  Each dataset is placed into its own group, and the actual GitLab
  project for a dataset is put in a project named "_repo_" inside
  this group. Using this layout, arbitrarily deep hierarchies of
  nested datasets can be represented, while the hierarchical structure
  is reflected in the project path. This is the default layout, if
  no project path is specified.
"flat"
  All datasets are placed in the same group. The name of a project
  is its relative path within the root dataset, with all path separator
  characters replaced by '--'.
"collection"
  This is a hybrid layout, where the root dataset is placed in a "_repo_"
  project inside a group, and all nested subdatasets are represented
  inside the group using a "flat" layout.

GitLab cannot host dataset content. However, in combination with
other data sources (and siblings), publishing a dataset to GitLab can
facilitate distribution and exchange, while still allowing any dataset
consumer to obtain actual data content from alternative sources.

*Configuration*

All configuration switches and options for GitLab sibling creation can
be provided arguments to the command. However, it is also possible to
specify a particular setup in a dataset's configuration. This is
particularly important when managing large collections of datasets.
Configuration options are:

"datalad.gitlab-default-site"
    Name of the default GitLab site (see --site)
"datalad.gitlab-SITENAME-siblingname"
    Name of the sibling configured for the local dataset that points
    to the GitLab instance SITENAME (see --name)
"datalad.gitlab-SITENAME-layout"
    Project layout used at the GitLab instance SITENAME (see --layout)
"datalad.gitlab-SITENAME-access"
    Access method used for the GitLab instance SITENAME (see --access)
"datalad.gitlab-SITENAME-project"
    Project location/path used for a datasets at GitLab instance
    SITENAME (see --project). Configuring this is useful for deriving
    project paths for subdatasets, relative to superdataset.


Options
-------
PATH
~~~~
selectively create siblings for any datasets underneath a given path. By default only the root dataset is considered.

**-h**, **-\\-help**, **-\\-help-np**
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
show this help message. --help-np forcefully disables the use of a pager for displaying the help message

**-\\-site** SITENAME
~~~~~~~~~~~~~~~~~~~~~
name of the GitLab site to create a sibling at. Must match an existing python- gitlab configuration section with location and authentication settings (see https://python-gitlab.readthedocs.io/en/stable/cli-usage.html#configuration). By default the dataset configuration is consulted. Constraints: value must be NONE, or value must be a string

**-\\-project** NAME/LOCATION
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
project name/location at the GitLab site. If a subdataset of the reference dataset is processed, its project path is automatically determined by the LAYOUT configuration, by default. Constraints: value must be NONE, or value must be a string

**-\\-layout** {hierarchy|collection|flat}
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
layout of projects at the GitLab site, if a collection, or a hierarchy of datasets and subdatasets is to be created. By default the dataset configuration is consulted. Constraints: value must be one of ('hierarchy', 'collection', 'flat')

**-\\-dataset** *DATASET*, **-d** *DATASET*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
reference or root dataset. If no path constraints are given, a sibling for this dataset will be created. In this and all other cases, the reference dataset is also consulted for the GitLab configuration, and desired project layout. If no dataset is given, an attempt is made to identify the dataset based on the current working directory. Constraints: Value must be a Dataset or a valid identifier of a Dataset (e.g. a path)

**-r**, **-\\-recursive**
~~~~~~~~~~~~~~~~~~~~~~~~~
if set, recurse into potential subdatasets.

**-R** LEVELS, **-\\-recursion-limit** LEVELS
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
limit recursion into subdatasets to the given number of levels. Constraints: value must be convertible to type 'int'

**-s** NAME, **-\\-name** NAME
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
name to represent the GitLab sibling remote in the local dataset installation. If not specified a name is looked up in the dataset configuration, or defaults to the SITE name. Constraints: value must be a string

**-\\-existing** {skip|error|reconfigure}
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
desired behavior when already existing or configured siblings are discovered. 'skip': ignore; 'error': fail, if access URLs differ; 'reconfigure': use the existing repository and reconfigure the local dataset to use it as a sibling. Constraints: value must be one of ('skip', 'error', 'reconfigure') [Default: 'error']

**-\\-access** {http|ssh|ssh+http}
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
access method used for data transfer to and from the sibling. 'ssh': read and write access used the SSH protocol; 'http': read and write access use HTTP requests; 'ssh+http': read access is done via HTTP and write access performed with SSH. Dataset configuration is consulted for a default, 'http' is used otherwise. Constraints: value must be one of ('http', 'ssh', 'ssh+http')

**-\\-publish-depends** SIBLINGNAME
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
add a dependency such that the given existing sibling is always published prior to the new sibling. This equals setting a configuration item 'remote.SIBLINGNAME.datalad-publish-depends'. This option can be given more than once to configure multiple dependencies. Constraints: value must be a string

**-\\-description** *DESCRIPTION*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
brief description for the GitLab project (displayed on the site). Constraints: value must be a string

**-\\-dryrun**
~~~~~~~~~~~~~~
Deprecated. Use the renamed ``--dry-run`` parameter.

**-\\-dry-run**
~~~~~~~~~~~~~~~
if set, no repository will be created, only tests for name collisions will be performed, and would-be repository names are reported for all relevant datasets.

**-\\-version**
~~~~~~~~~~~~~~~
show the module and its version which provides the command

Authors
-------
datalad is developed by The DataLad Team and Contributors <team@datalad.org>.
