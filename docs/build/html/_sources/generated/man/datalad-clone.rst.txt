.. _man_datalad-clone:

datalad clone
=============

Synopsis
--------
::

  datalad clone [-h] [-d DATASET] [-D DESCRIPTION] [--reckless
      [auto|ephemeral|shared-...]] [--version] SOURCE [PATH] ...

Description
-----------
Obtain a dataset (copy) from a URL or local directory

The purpose of this command is to obtain a new clone (copy) of a dataset
and place it into a not-yet-existing or empty directory. As such CLONE
provides a strict subset of the functionality offered by `install`. Only a
single dataset can be obtained, and immediate recursive installation of
subdatasets is not supported. However, once a (super)dataset is installed
via CLONE, any content, including subdatasets can be obtained by a
subsequent `get` command.

Primary differences over a direct `git clone` call are 1) the automatic
initialization of a dataset annex (pure Git repositories are equally
supported); 2) automatic registration of the newly obtained dataset as a
subdataset (submodule), if a parent dataset is specified; 3) support
for additional resource identifiers (DataLad resource identifiers as used
on datasets.datalad.org, and RIA store URLs as used for store.datalad.org
- optionally in specific versions as identified by a branch or a tag; see
examples); and 4) automatic configurable generation of alternative access
URL for common cases (such as appending '.git' to the URL in case the
accessing the base URL failed).

In case the clone is registered as a subdataset, the original URL passed to
CLONE is recorded in `.gitmodules` of the parent dataset in addition
to the resolved URL used internally for git-clone. This allows to preserve
datalad specific URLs like ria+ssh://... for subsequent calls to GET if
the subdataset was locally removed later on.



URL mapping configuration

'clone' supports the transformation of URLs via (multi-part) substitution
specifications. A substitution specification is defined as a configuration
setting 'datalad.clone.url-substition.<seriesID>' with a string containing
a match and substitution expression, each following Python's regular
expression syntax. Both expressions are concatenated to a single string
with an arbitrary delimiter character. The delimiter is defined by
prefixing the string with the delimiter. Prefix and delimiter are stripped
from the expressions (Example: ",^http://(.*)$,https://\1").  This setting
can be defined multiple times, using the same '<seriesID>'.  Substitutions
in a series will be applied incrementally, in order of their definition.
The first substitution in such a series must match, otherwise no further
substitutions in a series will be considered. However, following the first
match all further substitutions in a series are processed, regardless
whether intermediate expressions match or not. Substitution series themselves
have no particular order, each matching series will result in a candidate
clone URL. Consequently, the initial match specification in a series should
be as precise as possible to prevent inflation of candidate URLs.

SEEALSO

  handbook:3-001 (http://handbook.datalad.org/symbols)
    More information on Remote Indexed Archive (RIA) stores

*Examples*

Install a dataset from Github into the current directory::

   % datalad clone https://github.com/datalad-datasets/longnow-podcasts.git

Install a dataset into a specific directory::

   % datalad clone https://github.com/datalad-datasets/longnow-podcasts.git \
     myfavpodcasts

Install a dataset as a subdataset into the current dataset::

   % datalad clone -d . https://github.com/datalad-datasets/longnow-podcasts.git

Install the main superdataset from datasets.datalad.org::

   % datalad clone ///

Install a dataset identified by a literal alias from store.datalad.org::

   % datalad clone ria+http://store.datalad.org#~hcp-openaccess

Install a dataset in a specific version as identified by a branch or
tag name from store.datalad.org::

   % datalad clone ria+http://store.datalad.org#76b6ca66-36b1-11ea-a2e6-f0d5bf7b5561@myidentifier

Install a dataset with group-write access permissions::

   % datalad clone http://example.com/dataset --reckless shared-group




Options
-------
SOURCE
~~~~~~
URL, DataLad resource identifier, local path or instance of dataset to be cloned. Constraints: value must be a string

PATH
~~~~
path to clone into. If no PATH is provided a destination path will be derived from a source URL similar to git clone.

GIT CLONE OPTIONS
~~~~~~~~~~~~~~~~~
Options to pass to git clone. Any argument specified after SOURCE and the optional PATH will be passed to git-clone. Note that not all options will lead to viable results. For example '--single-branch' will not result in a functional annex repository because both a regular branch and the git-annex branch are required. Note that a version in a RIA URL takes precedence over '--branch'.

**-h**, **-\\-help**, **-\\-help-np**
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
show this help message. --help-np forcefully disables the use of a pager for displaying the help message

**-d** *DATASET*, **-\\-dataset** *DATASET*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
(parent) dataset to clone into. If given, the newly cloned dataset is registered as a subdataset of the parent. Also, if given, relative paths are interpreted as being relative to the parent dataset, and not relative to the working directory. Constraints: Value must be a Dataset or a valid identifier of a Dataset (e.g. a path)

**-D** *DESCRIPTION*, **-\\-description** *DESCRIPTION*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
short description to use for a dataset location. Its primary purpose is to help humans to identify a dataset copy (e.g., "mike's dataset on lab server"). Note that when a dataset is published, this information becomes available on the remote side. Constraints: value must be a string

**-\\-reckless** [auto|ephemeral|shared-...]
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Obtain a dataset or subdatset and set it up in a potentially unsafe way for performance, or access reasons. Use with care, any dataset is marked as 'untrusted'. The reckless mode is stored in a dataset's local configuration under 'datalad.clone.reckless', and will be inherited to any of its subdatasets. Supported modes are: ['auto']: hard-link files between local clones. In-place modification in any clone will alter original annex content. ['ephemeral']: symlink annex to origin's annex and discard local availability info via git- annex-dead 'here'. Shares an annex between origin and clone w/o git-annex being aware of it. In case of a change in origin you need to update the clone before you're able to save new content on your end. Alternative to 'auto' when hardlinks are not an option, or number of consumed inodes needs to be minimized. Note that this mode can only be used with clones from non-bare repositories or a RIA store! Otherwise two different annex object tree structures (dirhashmixed vs dirhashlower) will be used simultaneously, and annex keys using the respective other structure will be inaccessible. ['shared-<mode>']: set up repository and annex permission to enable multi-user access. This disables the standard write protection of annex'ed files. <mode> can be any value support by 'git init --shared=', such as 'group', or 'all'. Constraints: value must be one of (True, False, 'auto', 'ephemeral'), or value must start with 'shared-'

**-\\-version**
~~~~~~~~~~~~~~~
show the module and its version which provides the command

Authors
-------
datalad is developed by The DataLad Team and Contributors <team@datalad.org>.
