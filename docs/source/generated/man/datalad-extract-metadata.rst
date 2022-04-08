.. _man_datalad-extract-metadata:

datalad extract-metadata
========================

Synopsis
--------
::

  datalad extract-metadata [-h] --type NAME [-d DATASET] [--version] [FILE ...]

Description
-----------
Run one or more of DataLad's metadata extractors on a dataset or file.

The result(s) are structured like the metadata DataLad would extract
during metadata aggregation. There is one result per dataset/file.

Examples:

  Extract metadata with two extractors from a dataset in the current directory
  and also from all its files::

    $ datalad extract-metadata -d . --type frictionless_datapackage --type datalad_core

  Extract XMP metadata from a single PDF that is not part of any dataset::

    $ datalad extract-metadata --type xmp Downloads/freshfromtheweb.pdf


Options
-------
FILE
~~~~
Path of a file to extract metadata from. Constraints: value must be a string

**-h**, **-\\-help**, **-\\-help-np**
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
show this help message. --help-np forcefully disables the use of a pager for displaying the help message

**-\\-type** NAME
~~~~~~~~~~~~~~~~~
Name of a metadata extractor to be executed. This option can be given more than once.

**-d** *DATASET*, **-\\-dataset** *DATASET*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
"Dataset to extract metadata from. If no FILE is given, metadata is extracted from all files of the dataset. Constraints: Value must be a Dataset or a valid identifier of a Dataset (e.g. a path)

**-\\-version**
~~~~~~~~~~~~~~~
show the module and its version which provides the command

Authors
-------
datalad is developed by The DataLad Team and Contributors <team@datalad.org>.
