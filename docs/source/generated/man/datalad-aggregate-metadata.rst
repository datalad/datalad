.. _man_datalad-aggregate-metadata:

datalad aggregate-metadata
==========================

Synopsis
--------
::

  datalad aggregate-metadata [-h] [-d DATASET] [-r] [-R LEVELS] [--update-mode {all|target}]
      [--incremental] [--force-extraction] [--nosave] [--version]
      [PATH ...]

Description
-----------
Aggregate metadata of one or more datasets for later query.

Metadata aggregation refers to a procedure that extracts metadata present
in a dataset into a portable representation that is stored a single
standardized format. Moreover, metadata aggregation can also extract
metadata in this format from one dataset and store it in another
(super)dataset. Based on such collections of aggregated metadata it is
possible to discover particular datasets and specific parts of their
content, without having to obtain the target datasets first (see the
DataLad 'search' command).

To enable aggregation of metadata that are contained in files of a dataset,
one has to enable one or more metadata extractor for a dataset. DataLad
supports a number of common metadata standards, such as the Exchangeable
Image File Format (EXIF), Adobe's Extensible Metadata Platform (XMP), and
various audio file metadata systems like ID3. DataLad extension packages
can provide metadata data extractors for additional metadata sources. For
example, the neuroimaging extension provides extractors for scientific
(meta)data standards like BIDS, DICOM, and NIfTI1.  Some metadata
extractors depend on particular 3rd-party software. The list of metadata
extractors available to a particular DataLad installation is reported by
the 'wtf' command ('datalad wtf').

Enabling a metadata extractor for a dataset is done by adding its name to the
'datalad.metadata.nativetype' configuration variable -- typically in the
dataset's configuration file (.datalad/config), e.g.::

  [datalad "metadata"]
    nativetype = exif
    nativetype = xmp

If an enabled metadata extractor is not available in a particular DataLad
installation, metadata extraction will not succeed in order to avoid
inconsistent aggregation results.

Enabling multiple extractors is supported. In this case, metadata are
extracted by each extractor individually, and stored alongside each other.
Metadata aggregation will also extract DataLad's own metadata (extractors
'datalad_core', and 'annex').

Metadata aggregation can be performed recursively, in order to aggregate all
metadata across all subdatasets, for example, to be able to search across
any content in any dataset of a collection. Aggregation can also be performed
for subdatasets that are not available locally. In this case, pre-aggregated
metadata from the closest available superdataset will be considered instead.

Depending on the versatility of the present metadata and the number of dataset
or files, aggregated metadata can grow prohibitively large. A number of
configuration switches are provided to mitigate such issues.

datalad.metadata.aggregate-content-<extractor-name>
  If set to false, content metadata aggregation will not be performed for
  the named metadata extractor (a potential underscore '_' in the extractor name must
  be replaced by a dash '-'). This can substantially reduce the runtime for
  metadata extraction, and also reduce the size of the generated metadata
  aggregate. Note, however, that some extractors may not produce any metadata
  when this is disabled, because their metadata might come from individual
  file headers only. 'datalad.metadata.store-aggregate-content' might be
  a more appropriate setting in such cases.

datalad.metadata.aggregate-ignore-fields
  Any metadata key matching any regular expression in this configuration setting
  is removed prior to generating the dataset-level metadata summary (keys
  and their unique values across all dataset content), and from the dataset
  metadata itself. This switch can also be used to filter out sensitive
  information prior aggregation.

datalad.metadata.generate-unique-<extractor-name>
  If set to false, DataLad will not auto-generate a summary of unique content
  metadata values for a particular extractor as part of the dataset-global metadata
  (a potential underscore '_' in the extractor name must be replaced by a dash '-').
  This can be useful if such a summary is bloated due to minor uninformative (e.g.
  numerical) differences, or when a particular extractor already provides a
  carefully designed content metadata summary.

datalad.metadata.maxfieldsize
  Any metadata value that exceeds the size threshold given by this configuration
  setting (in bytes/characters) is removed.

datalad.metadata.store-aggregate-content
  If set, extracted content metadata are still used to generate a dataset-level
  summary of present metadata (all keys and their unique values across all
  files in a dataset are determined and stored as part of the dataset-level
  metadata aggregate, see datalad.metadata.generate-unique-<extractor-name>),
  but metadata on individual files are not stored.
  This switch can be used to avoid prohibitively large metadata files. Discovery
  of datasets containing content matching particular metadata properties will
  still be possible, but such datasets would have to be obtained first in order
  to discover which particular files in them match these properties.


Options
-------
PATH
~~~~
path to datasets that shall be aggregated. When a given path is pointing into a dataset, the metadata of the containing dataset will be aggregated. If no paths given, current dataset metadata is aggregated. Constraints: value must be a string

**-h**, **-\\-help**, **-\\-help-np**
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
show this help message. --help-np forcefully disables the use of a pager for displaying the help message

**-d** *DATASET*, **-\\-dataset** *DATASET*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
topmost dataset metadata will be aggregated into. All dataset between this dataset and any given path will receive updated aggregated metadata from all given paths. Constraints: Value must be a Dataset or a valid identifier of a Dataset (e.g. a path)

**-r**, **-\\-recursive**
~~~~~~~~~~~~~~~~~~~~~~~~~
if set, recurse into potential subdatasets.

**-R** LEVELS, **-\\-recursion-limit** LEVELS
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
limit recursion into subdatasets to the given number of levels. Constraints: value must be convertible to type 'int'

**-\\-update-mode** {all|target}
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
which datasets to update with newly aggregated metadata: all datasets from any leaf dataset to the top-level target dataset including all intermediate datasets (all), or just the top-level target dataset (target). Constraints: value must be one of ('all', 'target') [Default: 'target']

**-\\-incremental**
~~~~~~~~~~~~~~~~~~~
If set, all information on metadata records of subdatasets that have not been (re-)aggregated in this run will be kept unchanged. This is useful when (re-)aggregation only a subset of a dataset hierarchy, for example, because not all subdatasets are locally available.

**-\\-force-extraction**
~~~~~~~~~~~~~~~~~~~~~~~~
If set, all enabled extractors will be engaged regardless of whether change detection indicates that metadata has already been extracted for a given dataset state.

**-\\-nosave**
~~~~~~~~~~~~~~
by default all modifications to a dataset are immediately saved. Giving this option will disable this behavior.

**-\\-version**
~~~~~~~~~~~~~~~
show the module and its version which provides the command

Authors
-------
datalad is developed by The DataLad Team and Contributors <team@datalad.org>.
