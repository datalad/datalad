.. _man_datalad-search:

datalad search
==============

Synopsis
--------
::

  datalad search [-h] [-d DATASET] [--reindex] [--max-nresults MAX_NRESULTS] [--mode
      {egrep,textblob,autofield}] [--full-record] [--show-keys
      {name,short,full}] [--show-query] [--version] [QUERY ...]

Description
-----------
Search dataset metadata

DataLad can search metadata extracted from a dataset and/or aggregated into
a superdataset (see the `aggregate-metadata` command). This makes it
possible to discover datasets, or individual files in a dataset even when
they are not available locally.

Ultimately DataLad metadata are a graph of linked data structures. However,
this command does not (yet) support queries that can exploit all
information stored in the metadata. At the moment the following search
modes are implemented that represent different trade-offs between the
expressiveness of a query and the computational and storage resources
required to execute a query.

- egrep (default)

- egrepcs [case-sensitive egrep]

- textblob

- autofield

An alternative default mode can be configured by tuning the
configuration variable 'datalad.search.default-mode'::

  [datalad "search"]
    default-mode = egrepcs

Each search mode has its own default configuration for what kind of
documents to query. The respective default can be changed via configuration
variables::

  [datalad "search"]
    index-<mode_name>-documenttype = (all|datasets|files)


*Mode: egrep/egrepcs*

These search modes are largely ignorant of the metadata structure, and
simply perform matching of a search pattern against a flat
string-representation of metadata. This is advantageous when the query is
simple and the metadata structure is irrelevant, or precisely known.
Moreover, it does not require a search index, hence results can be reported
without an initial latency for building a search index when the underlying
metadata has changed (e.g. due to a dataset update). By default, these
search modes only consider datasets and do not investigate records for
individual files for speed reasons. Search results are reported in the
order in which they were discovered.

Queries can make use of Python regular expression syntax
(https://docs.python.org/3/library/re.html). In EGREP mode, matching is
case-insensitive when the query does not contain upper case characters, but
is case-sensitive when it does. In `egrepcs` mode, matching is always
case-sensitive. Expressions will match anywhere in a metadata string, not
only at the start.

When multiple queries are given, all queries have to match for a search hit
(AND behavior).

It is possible to search individual metadata key/value items by prefixing
the query with a metadata key name, separated by a colon (':'). The key
name can also be a regular expression to match multiple keys. A query match
happens when any value of an item with a matching key name matches the query
(OR behavior). See examples for more information.

Examples:

  Query for (what happens to be) an author::

    % datalad search haxby

  Queries are case-INsensitive when the query contains no upper case characters,
  and can be regular expressions. Use EGREPCS mode when it is desired
  to perform a case-sensitive lowercase match::

    % datalad search --mode egrepcs halchenko.*haxby

  This search mode performs NO analysis of the metadata content.  Therefore
  queries can easily fail to match. For example, the above query implicitly
  assumes that authors are listed in alphabetical order.  If that is the
  case (which may or may not be true), the following query would yield NO
  hits::

    % datalad search Haxby.*Halchenko

  The ``textblob`` search mode represents an alternative that is more
  robust in such cases.

  For more complex queries multiple query expressions can be provided that
  all have to match to be considered a hit (AND behavior). This query
  discovers all files (non-default behavior) that match 'bids.type=T1w'
  AND 'nifti1.qform_code=scanner'::

    % datalad -c datalad.search.index-egrep-documenttype=all search bids.type:T1w nifti1.qform_code:scanner

  Key name selectors can also be expressions, which can be used to select
  multiple keys or construct "fuzzy" queries. In such cases a query matches
  when any item with a matching key matches the query (OR behavior).
  However, multiple queries are always evaluated using an AND conjunction.
  The following query extends the example above to match any files that
  have either 'nifti1.qform_code=scanner' or 'nifti1.sform_code=scanner'::

    % datalad -c datalad.search.index-egrep-documenttype=all search bids.type:T1w nifti1.(q|s)form_code:scanner

*Mode: textblob*

This search mode is very similar to the ``egrep`` mode, but with a few key
differences. A search index is built from the string-representation of
metadata records. By default, only datasets are included in this index, hence
the indexing is usually completed within a few seconds, even for hundreds
of datasets. This mode uses its own query language (not regular expressions)
that is similar to other search engines. It supports logical conjunctions
and fuzzy search terms. More information on this is available from the Whoosh
project (search engine implementation):

  - Description of the Whoosh query language:
    http://whoosh.readthedocs.io/en/latest/querylang.html)

  - Description of a number of query language customizations that are
    enabled in DataLad, such as, fuzzy term matching:
    http://whoosh.readthedocs.io/en/latest/parsing.html#common-customizations

Importantly, search hits are scored and reported in order of descending
relevance, hence limiting the number of search results is more meaningful
than in the 'egrep' mode and can also reduce the query duration.

Examples:

  Search for (what happens to be) two authors, regardless of the order in
  which those names appear in the metadata::

    % datalad search --mode textblob halchenko haxby

  Fuzzy search when you only have an approximate idea what you are looking
  for or how it is spelled::

    % datalad search --mode textblob haxbi~

  Very fuzzy search, when you are basically only confident about the first
  two characters and how it sounds approximately (or more precisely: allow
  for three edits and require matching of the first two characters)::

    % datalad search --mode textblob haksbi~3/2

  Combine fuzzy search with logical constructs::

    % datalad search --mode textblob 'haxbi~ AND (hanke OR halchenko)'


*Mode: autofield*

This mode is similar to the 'textblob' mode, but builds a vastly more
detailed search index that represents individual metadata variables as
individual fields. By default, this search index includes records for
datasets and individual fields, hence it can grow very quickly into
a huge structure that can easily take an hour or more to build and require
more than a GB of storage. However, limiting it to documents on datasets
(see above) retains the enhanced expressiveness of queries while
dramatically reducing the resource demands.

Examples:

  List names of search index fields (auto-discovered from the set of
  indexed datasets) which either have a field starting with "age" or
  "gender"::

    % datalad search --mode autofield --show-keys name '\.age' '\.gender'

  Fuzzy search for datasets with an author that is specified in a particular
  metadata field::

    % datalad search --mode autofield bids.author:haxbi~ type:dataset

  Search for individual files that carry a particular description
  prefix in their 'nifti1' metadata::

    % datalad search --mode autofield nifti1.description:FSL* type:file


*Reporting*

Search hits are returned as standard DataLad results. On the command line
the '--output-format' (or '-f') option can be used to tweak results for
further processing.

Examples:

  Format search hits as a JSON stream (one hit per line)::

    % datalad -f json search haxby

  Custom formatting: which terms matched the query of particular
  results. Useful for investigating fuzzy search results::

    $ datalad -f '{path}: {query_matched}' search --mode autofield bids.author:haxbi~


Options
-------
QUERY
~~~~~
query string, supported syntax and features depends on the selected search mode (see documentation).

**-h**, **-\\-help**, **-\\-help-np**
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
show this help message. --help-np forcefully disables the use of a pager for displaying the help message

**-d** *DATASET*, **-\\-dataset** *DATASET*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
specify the dataset to perform the query operation on. If no dataset is given, an attempt is made to identify the dataset based on the current working directory and/or the PATH given. Constraints: Value must be a Dataset or a valid identifier of a Dataset (e.g. a path)

**-\\-reindex**
~~~~~~~~~~~~~~~
force rebuilding the search index, even if no change in the dataset's state has been detected, for example, when the index documenttype configuration has changed.

**-\\-max-nresults** *MAX_NRESULTS*
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
maxmimum number of search results to report. Setting this to 0 will report all search matches. Depending on the mode this can search substantially slower. If not specified, a mode-specific default setting will be used. Constraints: value must be convertible to type 'int'

**-\\-mode** {egrep,textblob,autofield}
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Mode of search index structure and content. See section SEARCH MODES for details.

**-\\-full-record**, **-f**
~~~~~~~~~~~~~~~~~~~~~~~~~~~
If set, return the full metadata record for each search hit. Depending on the search mode this might require additional queries. By default, only data that is available to the respective search modes is returned. This always includes essential information, such as the path and the type.

**-\\-show-keys** {name,short,full}
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
if given, a list of known search keys is shown. If 'name' - only the name is printed one per line. If 'short' or 'full', statistics (in how many datasets, and how many unique values) are printed. 'short' truncates the listing of unique values. QUERY, if provided, is regular expressions any of which keys should contain. No other action is performed (except for reindexing), even if other arguments are given. Each key is accompanied by a term definition in parenthesis (TODO). In most cases a definition is given in the form of a URL. If an ontology definition for a term is known, this URL can resolve to a webpage that provides a comprehensive definition of the term. However, for speed reasons term resolution is solely done on information contained in a local dataset's metadata, and definition URLs might be outdated or point to no longer existing resources.

**-\\-show-query**
~~~~~~~~~~~~~~~~~~
if given, the formal query that was generated from the given query string is shown, but not actually executed. This is mostly useful for debugging purposes.

**-\\-version**
~~~~~~~~~~~~~~~
show the module and its version which provides the command

Authors
-------
datalad is developed by The DataLad Team and Contributors <team@datalad.org>.
