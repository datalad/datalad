.. _man_datalad-create-sibling:

datalad create-sibling
======================

Synopsis
--------
::

  datalad create-sibling [-h] [-s [NAME]] [--target-dir PATH] [--target-url URL]
      [--target-pushurl URL] [--dataset DATASET] [-r] [-R LEVELS]
      [--existing MODE] [--shared
      {false|true|umask|group|all|world|everybody|0xxx}] [--group
      GROUP] [--ui {false|true|html_filename}] [--as-common-datasrc
      NAME] [--publish-by-default REFSPEC] [--publish-depends
      SIBLINGNAME] [--annex-wanted EXPR] [--annex-group EXPR]
      [--annex-groupwanted EXPR] [--inherit] [--since SINCE]
      [--version] [SSHURL]

Description
-----------
Create a dataset sibling on a UNIX-like Shell (local or SSH)-accessible machine

Given a local dataset, and a path or SSH login information this command
creates a remote dataset repository and configures it as a dataset sibling
to be used as a publication target (see PUBLISH command).

Various properties of the remote sibling can be configured (e.g. name
location on the server, read and write access URLs, and access
permissions.

Optionally, a basic web-viewer for DataLad datasets can be installed
at the remote location.

This command supports recursive processing of dataset hierarchies, creating
a remote sibling for each dataset in the hierarchy. By default, remote
siblings are created in hierarchical structure that reflects the
organization on the local file system. However, a simple templating
mechanism is provided to produce a flat list of datasets (see
--target-dir).


Options
-------
SSHURL
~~~~~~
Login information for the target server. This can be given as a URL (ssh://host/path), SSH-style (user@host:path) or just a local path. Unless overridden, this also serves the future dataset's access URL and path on the server. Constraints: value must be a string

**-h**, **-\\-help**, **-\\-help-np**
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
show this help message. --help-np forcefully disables the use of a pager for displaying the help message

**-s** [NAME], **-\\-name** [NAME]
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
sibling name to create for this publication target. If RECURSIVE is set, the same name will be used to label all the subdatasets' siblings. When creating a target dataset fails, no sibling is added. Constraints: value must be a string

**-\\-target-dir** PATH
~~~~~~~~~~~~~~~~~~~~~~~
path to the directory *on the server* where the dataset shall be created. By default this is set to the URL (or local path) specified via SSHURL. If a relative path is provided here, it is interpreted as being relative to the user's home directory on the server (or relative to SSHURL, when that is a local path). Additional features are relevant for recursive processing of datasets with subdatasets. By default, the local dataset structure is replicated on the server. However, it is possible to provide a template for generating different target directory names for all (sub)datasets. Templates can contain certain placeholder that are substituted for each (sub)dataset. For example: "/mydirectory/dataset%RELNAME". Supported placeholders: %RELNAME - the name of the datasets, with any slashes replaced by dashes. Constraints: value must be a string

**-\\-target-url** URL
~~~~~~~~~~~~~~~~~~~~~~
"public" access URL of the to-be-created target dataset(s) (default: SSHURL). Accessibility of this URL determines the access permissions of potential consumers of the dataset. As with `target_dir`, templates (same set of placeholders) are supported. Also, if specified, it is provided as the annex description. Constraints: value must be a string

**-\\-target-pushurl** URL
~~~~~~~~~~~~~~~~~~~~~~~~~~
In case the TARGET_URL cannot be used to publish to the dataset, this option specifies an alternative URL for this purpose. As with `target_url`, templates (same set of placeholders) are supported. Constraints: value must be a string

**-\\-dataset** *DATASET*, **-d** *DATASET*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
specify the dataset to create the publication target for. If no dataset is given, an attempt is made to identify the dataset based on the current working directory. Constraints: Value must be a Dataset or a valid identifier of a Dataset (e.g. a path)

**-r**, **-\\-recursive**
~~~~~~~~~~~~~~~~~~~~~~~~~
if set, recurse into potential subdatasets.

**-R** LEVELS, **-\\-recursion-limit** LEVELS
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
limit recursion into subdatasets to the given number of levels. Constraints: value must be convertible to type 'int'

**-\\-existing** MODE
~~~~~~~~~~~~~~~~~~~~~
action to perform, if a sibling is already configured under the given name and/or a target (non-empty) directory already exists. In this case, a dataset can be skipped ('skip'), the sibling configuration be updated ('reconfigure'), or process interrupts with error ('error'). DANGER ZONE: If 'replace' is used, an existing target directory will be forcefully removed, re-initialized, and the sibling (re-)configured (thus implies 'reconfigure'). REPLACE could lead to data loss, so use with care. To minimize possibility of data loss, in interactive mode DataLad will ask for confirmation, but it would raise an exception in non- interactive mode. Constraints: value must be one of ('skip', 'error', 'reconfigure', 'replace') [Default: 'error']

**-\\-shared** {false|true|umask|group|all|world|everybody|0xxx}
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
if given, configures the access permissions on the server for multi-users (this could include access by a webserver!). Possible values for this option are identical to those of `git init --shared` and are described in its documentation. Constraints: value must be a string, or value must be convertible to type bool

**-\\-group** GROUP
~~~~~~~~~~~~~~~~~~~
Filesystem group for the repository. Specifying the group is particularly important when --shared=group. Constraints: value must be a string

**-\\-ui** {false|true|html_filename}
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
publish a web interface for the dataset with an optional user-specified name for the html at publication target. defaults to `index.html` at dataset root. Constraints: value must be convertible to type bool, or value must be a string [Default: False]

**-\\-as-common-datasrc** NAME
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
configure the created sibling as a common data source of the dataset that can be automatically used by all consumers of the dataset (technical: git-annex auto- enabled special remote).

**-\\-publish-by-default** REFSPEC
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
add a refspec to be published to this sibling by default if nothing specified. Constraints: value must be a string

**-\\-publish-depends** SIBLINGNAME
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
add a dependency such that the given existing sibling is always published prior to the new sibling. This equals setting a configuration item 'remote.SIBLINGNAME.datalad-publish-depends'. This option can be given more than once to configure multiple dependencies. Constraints: value must be a string

**-\\-annex-wanted** EXPR
~~~~~~~~~~~~~~~~~~~~~~~~~
expression to specify 'wanted' content for the repository/sibling. See https://git-annex.branchable.com/git-annex-wanted/ for more information. Constraints: value must be a string

**-\\-annex-group** EXPR
~~~~~~~~~~~~~~~~~~~~~~~~
expression to specify a group for the repository. See https://git- annex.branchable.com/git-annex-group/ for more information. Constraints: value must be a string

**-\\-annex-groupwanted** EXPR
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
expression for the groupwanted. Makes sense only if --annex-wanted="groupwanted" and annex-group is given too. See https://git-annex.branchable.com/git-annex- groupwanted/ for more information. Constraints: value must be a string

**-\\-inherit**
~~~~~~~~~~~~~~~
if sibling is missing, inherit settings (git config, git annex wanted/group/groupwanted) from its super-dataset.

**-\\-since** *SINCE*
~~~~~~~~~~~~~~~~~~~~~
limit processing to subdatasets that have been changed since a given state (by tag, branch, commit, etc). This can be used to create siblings for recently added subdatasets. Constraints: value must be a string

**-\\-version**
~~~~~~~~~~~~~~~
show the module and its version which provides the command

Authors
-------
datalad is developed by The DataLad Team and Contributors <team@datalad.org>.
