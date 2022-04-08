.. _man_datalad-metadata:

datalad metadata
================

Synopsis
--------
::

  datalad metadata [-h] [-d DATASET] [--get-aggregates] [--reporton TYPE] [-r]
      [--version] [PATH ...]

Description
-----------
Metadata reporting for files and entire datasets

Two types of metadata are supported:

1. metadata describing a dataset as a whole (dataset-global metadata), and

2. metadata for files in a dataset (content metadata).

Both types can be accessed with this command.

Examples:

  Report the metadata of a single file, as aggregated into the closest
  locally available dataset, containing the query path::

    % datalad metadata somedir/subdir/thisfile.dat

  Sometimes it is helpful to get metadata records formatted in a more accessible
  form, here as pretty-printed JSON::

    % datalad -f json_pp metadata somedir/subdir/thisfile.dat

  Same query as above, but specify which dataset to query (must be
  containing the query path)::

    % datalad metadata -d . somedir/subdir/thisfile.dat

  Report any metadata record of any dataset known to the queried dataset::

    % datalad metadata --recursive --reporton datasets 

  Get a JSON-formatted report of aggregated metadata in a dataset, incl.
  information on enabled metadata extractors, dataset versions, dataset IDs,
  and dataset paths::

    % datalad -f json metadata --get-aggregates


Options
-------
PATH
~~~~
path(s) to query metadata for. Constraints: value must be a string

**-h**, **-\\-help**, **-\\-help-np**
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
show this help message. --help-np forcefully disables the use of a pager for displaying the help message

**-d** *DATASET*, **-\\-dataset** *DATASET*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
dataset to query. If given, metadata will be reported as stored in this dataset. Otherwise, the closest available dataset containing a query path will be consulted. Constraints: Value must be a Dataset or a valid identifier of a Dataset (e.g. a path)

**-\\-get-aggregates**
~~~~~~~~~~~~~~~~~~~~~~
if set, yields all (sub)datasets for which aggregate metadata are available in the dataset. No other action is performed, even if other arguments are given. The reported results contain a datasets's ID, the commit hash at which metadata aggregation was performed, and the location of the object file(s) containing the aggregated metadata.

**-\\-reporton** TYPE
~~~~~~~~~~~~~~~~~~~~~
choose on what type result to report on: 'datasets', 'files', 'all' (both datasets and files), or 'none' (no report). Constraints: value must be one of ('all', 'datasets', 'files', 'none') [Default: 'all']

**-r**, **-\\-recursive**
~~~~~~~~~~~~~~~~~~~~~~~~~
if set, recurse into potential subdatasets.

**-\\-version**
~~~~~~~~~~~~~~~
show the module and its version which provides the command

Authors
-------
datalad is developed by The DataLad Team and Contributors <team@datalad.org>.
