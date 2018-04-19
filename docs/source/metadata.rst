.. _chap_metadata:

Metadata
********

Overview
========

DataLad has built-in, modular, and extensible support for metadata in various
formats. Metadata is extracted from a dataset and its content by one or more
extractors that have to be enabled in a dataset's configuration. Extractors
yield metadata in a JSON-LD-like structure that can be arbitrarily complex and
deeply nested. Metadata from each extractor is kept unmodified, unmangled, and
separate from metadata of other extractors. This design enables tailored
applications using particular metadata that can use Datalad as a
content-agnostic aggregation and transport layer without being limited or
impacted by other metadata sources and schemas.

Extracted metadata is stored in a dataset in (compressed) files using a JSON
stream format, separately for metadata describing a dataset as a whole, and
metadata describing individual files in a dataset. This limits the amount of
metadata that has to be obtained and processed for applications that do not
require all available metadata.

DataLad provides a content-agnostic metadata aggregation mechanism that
stores metadata of sub-datasets (with arbitrary nesting levels) in a
superdataset, where it can then be queried without having the subdatasets
locally present.

Lastly, DataLad comes with a `search` command that enable metadata queries
via a flexible query language. However, alternative applications for metadata
queries (e.g. graph-based queries) can be built on DataLad, by requesting
a complete or partial dump of aggregated metadata available in a dataset.

.. _JSON-LD: http://json-ld.org/
.. _linked data: https://en.wikipedia.org/wiki/Linked_data


Supported metadata sources
==========================

This following sections provide an overview of included metadata extractors for
particular types of data structures and file formats.

Various audio file formats (``audio``)
--------------------------------------

This extractor uses the `mutagen <https://github.com/quodlibet/mutagen>`_
package to extract essential metadata from a range of audio file formats.  For
the most common metadata properties a constrained vocabulary, based on the
`Music Ontology <http://purl.org/ontology/mo/>`_ is employed.

datacite.org compliant datasets (``datacite``)
----------------------------------------------

This extractor can handle dataset-level metadata following the `datacite.org
<https://www.datacite.org>`_ specification. No constrained vocabulary is
identified at the moment.

Datalad's internal metadata storage (``datalad_core``)
------------------------------------------------------

This extractor can express Datalad's internal metadata representation, such
as the relationship of a super- and a subdataset. It uses DataLad's own
constrained vocabulary.

RFC822-compliant metadata (``datalad_rfc822``)
----------------------------------------------

This is a custom metadata format, inspired by the standard used for Debian
software packages that is particularly suited for manual entry. This format is
a good choice when metadata describing a dataset as a whole cannot be obtained
from some other structured format. The syntax is :rfc:`822`-compliant. In other
words: this is a text-based format that uses the syntax of email headers.
Metadata must be placed in ``DATASETROOT/.datalad/meta.rfc822`` for this format.

.. _RFC822: https://tools.ietf.org/html/rfc822

Here is an example:

.. code-block:: none

  Name: myamazingdataset
  Version: 1.0.0-rc3
  Description: Basic summary
   A text with arbitrary length and content that can span multiple
   .
   paragraphs (this is a new one)
  License: CC0
   The person who associated a work with this deed has dedicated the work to the
   public domain by waiving all of his or her rights to the work worldwide under
   copyright law, including all related and neighboring rights, to the extent
   allowed by law.
   .
   You can copy, modify, distribute and perform the work, even for commercial
   purposes, all without asking permission.
  Homepage: http://example.com
  Funding: Grandma's and Grandpa's support
  Issue-Tracker: https://github.com/datalad/datalad/issues
  Cite-As: Mike Author (2016). We made it. The breakthrough journal of unlikely
    events. 1, 23-453.
  DOI: 10.0000/nothere.48421

The following fields are supported:

``Audience``:
  A description of the target audience of the dataset.
``Author``:
  A comma-delimited list of authors of the dataset, preferably in the format.
  ``Firstname Lastname <Email Adress>``
``Cite-as``:
  Instructions on how to cite the dataset, or a structured citation.
``Description``:
  Description of the dataset as a whole. The first line should represent a
  compact short description with no more than 6-8 words.
``DOI``:
  A `digital object identifier <https://en.wikipedia.org/wiki/Digital_object_identifier>`_
  for the dataset.
``Funding``:
  Information on potential funding for the creation of the dataset and/or its
  content. This field can also be used to acknowledge non-monetary support.
``Homepage``:
  A URL to a project website for the dataset.
``Issue-tracker``:
  A URL to an issue tracker where known problems are documented and/or new
  reports can be submitted.
``License``:
  A description of the license or terms of use for the dataset. The first
  lines should contain a list of license labels (e.g. CC0, PPDL) for standard
  licenses, if possible. Full license texts or term descriptions can be
  included.
``Maintainer``:
  Can be used in addition and analog to ``Author``, when authors (creators of
  the data) need to be distinguished from maintainers of the dataset.
``Name``:
  A short name for the dataset. It may be beneficial to avoid special
  characters, umlauts, spaces, etc. to enable widespread use of this name
  for URL, catalog keys, etc. in unmodified form.
``Version``:
  A version for the dataset. This should be in a format that is alphanumerically
  sortable and lead to a "greater" version for an update of a dataset.

Metadata keys used by this extractor are defined in DataLad's own constrained
vocabulary.

Friction-less data packages (``frictionless_datapackage``)
----------------------------------------------------------

DataLad has basic support for extraction of essential dataset-level metadata
from `friction-less data packages
<http://specs.frictionlessdata.io/data-packages>`_ (``datapackage.json``).
file. Metadata keys are constrained to DataLad's own vocabulary.

Exchangeable Image File Format (``exif``)
-----------------------------------------

The extractor yields EXIF metadata from any compatible file. It uses
the W3C EXIF vocabulary (http://www.w3.org/2003/12/exif/ns/).

Various image/photo formats (``image``)
---------------------------------------

Standard image metadata is extractor using the `Pillow package
<https://github.com/python-pillow/Pillow>`_. Core metadata is available using
an adhoc vocabulary defined by the extractor.

Extensible Metadata Platform (``xmp``)
--------------------------------------

This extractor yields any XMP-compliant metadata from any supported file (e.g.
PDFs, photos). XMP metadata uses fully qualified terms from standard
vocabularies that are simply passed through by the extractor. At the moment
metadata extraction from side-car files is not supported, but would be easy to
add.

Metadata aggregation and query
==============================

Metadata aggregation can be performed with the :ref:`aggregate-metadata
<man_datalad-aggregate-metadata>` command. Aggregation is done for two
interrelated but distinct reasons:

- Fast uniform metadata access, independent of local data availability
- Comprehensive data discovery without access to or knowledge of individual
  datasets

In an individual dataset, metadata aggregation engages any number of enabled
metadata extractors to build a JSON-LD based metadata representation that is
separate from the original data files. These metadata objects are added to the
dataset and are tracked with the same mechanisms that are used for any other
dataset content. Based on this metadata, DataLad can provide fast and uniform
access to metadata for any dataset component (individual files, subdatasets,
the whole dataset itself), based on the relative path of a component within a
dataset (available via the :ref:`metadata <man_datalad-metadata>` command).
This extracted metadata can be kept or made available locally for any such
query, even when it is impossible or undesirable to keep the associated data
files around (e.g. due to size constraints).

For any superdataset (a dataset that contains subdatasets as components),
aggregation can go one step further. In this case, aggregation imports
extracted metadata from subdatasets into the superdataset to offer the just
described query feature for any aggregated subdataset too. This works across
any number of levels of nesting. For example, a subdataset that contains the
aggregated metadata for eight other datasets (that might have never been
available locally) can be aggregated into a local superdataset with all its
metadata. In that superdataset, a DataLad user is then able to query
information on any content of any subdataset, regardless of their actual
availability. This principle also allows any user to install the superdataset
from http://datasets.datalad.org and perform *local and offline* queries about
any dataset available online from this server.

Besides full access to all aggregated metadata by path (via the :ref:`metadata
<man_datalad-metadata>` command), DataLad also comes with a :ref:`search
<man_datalad-search>` command that provides different search modes to query the
entirety of the locally available metadata. Its capabilities include simple
keyword searches as well as more complex queries using date ranges or logical
conjunctions.


Vocabulary
==========

The following sections describe details and changes in the metadata
specifications implemented in datalad.

.. _2.0:

`v2.0 <http://docs.datalad.org/schema_v2.0.json>`_
--------------------------------------------------

* Current development version that will be released together with
  DataLad v0.10.

.. _1.0:

`v1.0 <http://docs.datalad.org/schema_v1.0.json>`_
--------------------------------------------------

* Original implementation that did not really see the light of the day.
