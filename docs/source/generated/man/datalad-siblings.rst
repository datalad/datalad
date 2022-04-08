.. _man_datalad-siblings:

datalad siblings
================

Synopsis
--------
::

  datalad siblings [-h] [-d DATASET] [-s NAME] [--url [URL]] [--pushurl PUSHURL] [-D
      DESCRIPTION] [--fetch] [--as-common-datasrc NAME]
      [--publish-depends SIBLINGNAME] [--publish-by-default REFSPEC]
      [--annex-wanted EXPR] [--annex-required EXPR] [--annex-group
      EXPR] [--annex-groupwanted EXPR] [--inherit] [--no-annex-info]
      [-r] [-R LEVELS] [--version]
      [{query|add|remove|configure|enable}]

Description
-----------
Manage sibling configuration

This command offers four different actions: 'query', 'add', 'remove',
'configure', 'enable'. 'query' is the default action and can be used to obtain
information about (all) known siblings. 'add' and 'configure' are highly
similar actions, the only difference being that adding a sibling
with a name that is already registered will fail, whereas
re-configuring a (different) sibling under a known name will not
be considered an error. 'enable' can be used to complete access
configuration for non-Git sibling (aka git-annex special remotes).
Lastly, the 'remove' action allows for the
removal (or de-configuration) of a registered sibling.

For each sibling (added, configured, or queried) all known sibling
properties are reported. This includes:

"name"
    Name of the sibling

"path"
    Absolute path of the dataset

"url"
    For regular siblings at minimum a "fetch" URL, possibly also a
    "pushurl"

Additionally, any further configuration will also be reported using
a key that matches that in the Git configuration.

By default, sibling information is rendered as one line per sibling
following this scheme::

  <dataset_path>: <sibling_name>(<+|->) [<access_specification]

where the `+` and `-` labels indicate the presence or absence of a
remote data annex at a particular remote, and ACCESS_SPECIFICATION
contains either a URL and/or a type label for the sibling.


Options
-------
{query|add|remove|configure|enable}
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
command action selection (see general documentation). Constraints: value must be one of ('query', 'add', 'remove', 'configure', 'enable') [Default: 'query']

**-h**, **-\\-help**, **-\\-help-np**
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
show this help message. --help-np forcefully disables the use of a pager for displaying the help message

**-d** *DATASET*, **-\\-dataset** *DATASET*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
specify the dataset to configure. If no dataset is given, an attempt is made to identify the dataset based on the input and/or the current working directory. Constraints: Value must be a Dataset or a valid identifier of a Dataset (e.g. a path)

**-s** NAME, **-\\-name** NAME
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
name of the sibling. For addition with path "URLs" and sibling removal this option is mandatory, otherwise the hostname part of a given URL is used as a default. This option can be used to limit 'query' to a specific sibling. Constraints: value must be a string

**-\\-url** [*URL*]
~~~~~~~~~~~~~~~~~~~
the URL of or path to the dataset sibling named by NAME. For recursive operation it is required that a template string for building subdataset sibling URLs is given. List of currently available placeholders: %NAME the name of the dataset, where slashes are replaced by dashes. Constraints: value must be a string

**-\\-pushurl** *PUSHURL*
~~~~~~~~~~~~~~~~~~~~~~~~~
in case the URL cannot be used to publish to the dataset sibling, this option specifies a URL to be used instead. If no `url` is given, PUSHURL serves as `url` as well. Constraints: value must be a string

**-D** *DESCRIPTION*, **-\\-description** *DESCRIPTION*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
short description to use for a dataset location. Its primary purpose is to help humans to identify a dataset copy (e.g., "mike's dataset on lab server"). Note that when a dataset is published, this information becomes available on the remote side. Constraints: value must be a string

**-\\-fetch**
~~~~~~~~~~~~~
fetch the sibling after configuration.

**-\\-as-common-datasrc** NAME
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
configure a sibling as a common data source of the dataset that can be automatically used by all consumers of the dataset. The sibling must be a regular Git remote with a configured HTTP(S) URL.

**-\\-publish-depends** SIBLINGNAME
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
add a dependency such that the given existing sibling is always published prior to the new sibling. This equals setting a configuration item 'remote.SIBLINGNAME.datalad-publish-depends'. This option can be given more than once to configure multiple dependencies. Constraints: value must be a string

**-\\-publish-by-default** REFSPEC
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
add a refspec to be published to this sibling by default if nothing specified. Constraints: value must be a string

**-\\-annex-wanted** EXPR
~~~~~~~~~~~~~~~~~~~~~~~~~
expression to specify 'wanted' content for the repository/sibling. See https://git-annex.branchable.com/git-annex-wanted/ for more information. Constraints: value must be a string

**-\\-annex-required** EXPR
~~~~~~~~~~~~~~~~~~~~~~~~~~~
expression to specify 'required' content for the repository/sibling. See https://git-annex.branchable.com/git-annex-required/ for more information. Constraints: value must be a string

**-\\-annex-group** EXPR
~~~~~~~~~~~~~~~~~~~~~~~~
expression to specify a group for the repository. See https://git- annex.branchable.com/git-annex-group/ for more information. Constraints: value must be a string

**-\\-annex-groupwanted** EXPR
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
expression for the groupwanted. Makes sense only if --annex-wanted="groupwanted" and annex-group is given too. See https://git-annex.branchable.com/git-annex- groupwanted/ for more information. Constraints: value must be a string

**-\\-inherit**
~~~~~~~~~~~~~~~
if sibling is missing, inherit settings (git config, git annex wanted/group/groupwanted) from its super-dataset.

**-\\-no-annex-info**
~~~~~~~~~~~~~~~~~~~~~
Whether to query all information about the annex configurations of siblings. Can be disabled if speed is a concern.

**-r**, **-\\-recursive**
~~~~~~~~~~~~~~~~~~~~~~~~~
if set, recurse into potential subdatasets.

**-R** LEVELS, **-\\-recursion-limit** LEVELS
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
limit recursion into subdatasets to the given number of levels. Constraints: value must be convertible to type 'int'

**-\\-version**
~~~~~~~~~~~~~~~
show the module and its version which provides the command

Authors
-------
datalad is developed by The DataLad Team and Contributors <team@datalad.org>.
