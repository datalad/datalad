.. _man_datalad-no-annex:

datalad no-annex
================

Synopsis
--------
::

  datalad no-annex [-h] [-d DATASET] [--pattern PATTERN [PATTERN ...]] [--ref-dir
      REF_DIR] [--makedirs] [--version]

Description
-----------
Configure a dataset to never put some content into the dataset's annex

This can be useful in mixed datasets that also contain textual data, such
as source code, which can be efficiently and more conveniently managed
directly in Git.

Patterns generally look like this::

  code/*

which would match all file in the code directory. In order to match all
files under ``code/``, including all its subdirectories use such a
pattern::

  code/**

Note that this command works incrementally, hence any existing configuration
(e.g. from a previous plugin run) is amended, not replaced.


Options
-------
**-h**, **-\\-help**, **-\\-help-np**
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
show this help message. --help-np forcefully disables the use of a pager for displaying the help message

**-d** *DATASET*, **-\\-dataset** *DATASET*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
"specify the dataset to configure. If no dataset is given, an attempt is made to identify the dataset based on the current working directory. Constraints: Value must be a Dataset or a valid identifier of a Dataset (e.g. a path)

**-\\-pattern** *PATTERN* [*PATTERN* ...]
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
list of path patterns. Any content whose path is matching any pattern will not be annexed when added to a dataset, but instead will be tracked directly in Git. Path pattern have to be relative to the directory given by the REF_DIR option. By default, patterns should be relative to the root of the dataset.

**-\\-ref-dir** *REF_DIR*
~~~~~~~~~~~~~~~~~~~~~~~~~
Relative path (within the dataset) to the directory that is to be configured. All patterns are interpreted relative to this path, and configuration is written to a ``.gitattributes`` file in this directory. [Default: '.']

**-\\-makedirs**
~~~~~~~~~~~~~~~~
If set, any missing directories will be created in order to be able to place a file into ``--ref-dir``.

**-\\-version**
~~~~~~~~~~~~~~~
show the module and its version which provides the command

Authors
-------
datalad is developed by The DataLad Team and Contributors <team@datalad.org>.
