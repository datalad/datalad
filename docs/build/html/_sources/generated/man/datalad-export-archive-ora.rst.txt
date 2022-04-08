.. _man_datalad-export-archive-ora:

datalad export-archive-ora
==========================

Synopsis
--------
::

  datalad export-archive-ora [-h] [-d DATASET] [--for LABEL] [--annex-wanted FILTERS] [--from FROM
      [FROM ...]] [--missing-content {error|continue|ignore}]
      [--version] TARGET ...

Description
-----------
Export an archive of a local annex object store for the ORA remote.

Keys in the local annex object store are reorganized in a temporary
directory (using links to avoid storage duplication) to use the
'hashdirlower' setup used by git-annex for bare repositories and
the directory-type special remote. This alternative object store is
then moved into a 7zip archive that is suitable for use in a
ORA remote dataset store. Placing such an archive into::

  <dataset location>/archives/archive.7z

Enables the ORA special remote to locate and retrieve all keys contained
in the archive.


Options
-------
TARGET
~~~~~~
if an existing directory, an 'archive.7z' is placed into it, otherwise this is the path to the target archive. Constraints: value must be a string

...
~~~
list of options for 7z to replace the default '-mx0' to generate an uncompressed archive.

**-h**, **-\\-help**, **-\\-help-np**
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
show this help message. --help-np forcefully disables the use of a pager for displaying the help message

**-d** *DATASET*, **-\\-dataset** *DATASET*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
specify the dataset to process. If no dataset is given, an attempt is made to identify the dataset based on the current working directory. Constraints: Value must be a Dataset or a valid identifier of a Dataset (e.g. a path)

**-\\-for** LABEL
~~~~~~~~~~~~~~~~~
name of the target sibling, wanted/preferred settings will be used to filter the files added to the archives. Constraints: value must be a string

**-\\-annex-wanted** FILTERS
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
git-annex-preferred-content expression for git-annex find to filter files. Should start with 'or' or 'and' when used in combination with `--for`.

**-\\-from** FROM [FROM ...]
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
one or multiple tree-ish from which to select files.

**-\\-missing-content** {error|continue|ignore}
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
By default, any discovered file with missing content will result in an error and the export is aborted. Setting this to 'continue' will issue warnings instead of failing on error. The value 'ignore' will only inform about problem at the 'debug' log level. The latter two can be helpful when generating a TAR archive from a dataset where some file content is not available locally. Constraints: value must be one of ('error', 'continue', 'ignore') [Default: 'error']

**-\\-version**
~~~~~~~~~~~~~~~
show the module and its version which provides the command

Authors
-------
datalad is developed by The DataLad Team and Contributors <team@datalad.org>.
