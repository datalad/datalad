.. _man_datalad-add-archive-content:

datalad add-archive-content
===========================

Synopsis
--------
::

  datalad add-archive-content [-h] [-d DATASET] [--annex ANNEX] [--add-archive-leading-dir]
      [--strip-leading-dirs] [--leading-dirs-depth LEADING_DIRS_DEPTH]
      [--leading-dirs-consider LEADING_DIRS_CONSIDER]
      [--use-current-dir] [-D] [--key] [-e EXCLUDE] [-r RENAME]
      [--existing {fail,overwrite,archive-suffix,numeric-suffix}] [-o
      ANNEX_OPTIONS] [--copy] [--no-commit] [--allow-dirty] [--stats
      STATS] [--drop-after] [--delete-after] [--version] archive

Description
-----------
Add content of an archive under git annex control.

Given an already annex'ed archive, extract and add its files to the
dataset, and reference the original archive as a custom special remote.

*Examples*

Add files from the archive 'big_tarball.tar.gz', but
keep big_tarball.tar.gz in the index::

   % datalad add-archive-content big_tarball.tar.gz

Add files from the archive 'tarball.tar.gz', and
remove big_tarball.tar.gz from the index::

   % datalad add-archive-content big_tarball.tar.gz --delete

Add files from the archive 's3.zip' but remove the leading
directory::

   % datalad add-archive-content s3.zip --strip-leading-dirs




Options
-------
archive
~~~~~~~
archive file or a key (if --key specified). Constraints: value must be a string

**-h**, **-\\-help**, **-\\-help-np**
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
show this help message. --help-np forcefully disables the use of a pager for displaying the help message

**-d** *DATASET*, **-\\-dataset** *DATASET*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
"specify the dataset to save. Constraints: Value must be a Dataset or a valid identifier of a Dataset (e.g. a path)

**-\\-annex** *ANNEX*
~~~~~~~~~~~~~~~~~~~~~
DEPRECATED. Use the 'dataset' parameter instead.

**-\\-add-archive-leading-dir**
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
place extracted content under a directory which would correspond to the archive name with all suffixes stripped. E.g. the content of `archive.tar.gz` will be extracted under `archive/`.

**-\\-strip-leading-dirs**
~~~~~~~~~~~~~~~~~~~~~~~~~~
remove one or more leading directories from the archive layout on extraction.

**-\\-leading-dirs-depth** *LEADING_DIRS_DEPTH*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
maximum depth of leading directories to strip. If not specified (None), no limit.

**-\\-leading-dirs-consider** *LEADING_DIRS_CONSIDER*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
regular expression(s) for directories to consider to strip away. Constraints: value must be a string

**-\\-use-current-dir**
~~~~~~~~~~~~~~~~~~~~~~~
extract the archive under the current directory, not the directory where the archive is located. This parameter is applied automatically if --key was used.

**-D**, **-\\-delete**
~~~~~~~~~~~~~~~~~~~~~~
delete original archive from the filesystem/Git in current tree. Note that it will be of no effect if --key is given.

**-\\-key**
~~~~~~~~~~~
signal if provided archive is not actually a filename on its own but an annex key. The archive will be extracted in the current directory.

**-e** *EXCLUDE*, **-\\-exclude** *EXCLUDE*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
regular expressions for filenames which to exclude from being added to annex. Applied after --rename if that one is specified. For exact matching, use anchoring. Constraints: value must be a string

**-r** *RENAME*, **-\\-rename** *RENAME*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
regular expressions to rename files before added them under to Git. The first defines how to split provided string into two parts: Python regular expression (with groups), and replacement string. Constraints: value must be a string

**-\\-existing** {fail,overwrite,archive-suffix,numeric-suffix}
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
what operation to perform if a file from an archive tries to overwrite an existing file with the same name. 'fail' (default) leads to an error result, 'overwrite' silently replaces existing file, 'archive-suffix' instructs to add a suffix (prefixed with a '-') matching archive name from which file gets extracted, and if that one is present as well, 'numeric-suffix' is in effect in addition, when incremental numeric suffix (prefixed with a '.') is added until no name collision is longer detected. [Default: 'fail']

**-o** *ANNEX_OPTIONS*, **-\\-annex-options** *ANNEX_OPTIONS*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
additional options to pass to git-annex. Constraints: value must be a string

**-\\-copy**
~~~~~~~~~~~~
copy the content of the archive instead of moving.

**-\\-no-commit**
~~~~~~~~~~~~~~~~~
don't commit upon completion.

**-\\-allow-dirty**
~~~~~~~~~~~~~~~~~~~
flag that operating on a dirty repository (uncommitted or untracked content) is ok.

**-\\-stats** *STATS*
~~~~~~~~~~~~~~~~~~~~~
ActivityStats instance for global tracking.

**-\\-drop-after**
~~~~~~~~~~~~~~~~~~
drop extracted files after adding to annex.

**-\\-delete-after**
~~~~~~~~~~~~~~~~~~~~
extract under a temporary directory, git-annex add, and delete afterwards. To be used to "index" files within annex without actually creating corresponding files under git. Note that `annex dropunused` would later remove that load.

**-\\-version**
~~~~~~~~~~~~~~~
show the module and its version which provides the command

Authors
-------
datalad is developed by The DataLad Team and Contributors <team@datalad.org>.
