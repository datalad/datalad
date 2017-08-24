.. _chap_metadata:

Meta data
*********

Overview
========

DataLad has built-in, modular, and extensible support for meta data in various
formats. The core concept is that meta data is accessed via dedicated parsers
in their native format, avoiding the need for mandatory conversion into a
"standard" format. Via these parser datalad is capable of performing a certain
amount of meta data homogenization, and standardization into a JSON-LD_
compliant `linked data`_ structure for the purpose of meta data aggregation in
:term:`superdataset`\ s.  Through this mechanism it is possible to obtain and
query meta data of any number of :term:`subdataset`\ s without the need to
actually install them.

.. _JSON-LD: http://json-ld.org/
.. _linked data: https://en.wikipedia.org/wiki/Linked_data

Sample datasets with meta data
==============================

http://datasets.datalad.org superdataset contains a collection of datasets
which we have prepared primarily from available online data resources such
as OpenfMRI_, CRCNS_, etc.  Many of those datasets came with meta data in
their native formats, such as `Brain Imaging Data Structure (BIDS)`_.  DataLad has
:ref:`aggregated <man_datalad-aggregate-metadata>` metadata where it was available
to enable basic :ref:`search <man_datalad-search>` queries.  If you
run :ref:`search <man_datalad-search>` command outside of any datalad dataset,
it will offer to install our http://datasets.datalad.org superdataset at
`~/datalad` and then search through its metadata.  If that superdataset is already
installed (by :ref:`datalad search <man_datalad-search>` or manually via
`datalad install -s /// ~/datalad`), you can refer to it in the search command
using `-d ///` option, e.g.::

    $> datalad search -d /// bids
    /home/yoh/datalad/openfmri/ds000017A
    /home/yoh/datalad/openfmri/ds000017
    /home/yoh/datalad/dicoms/dartmouth-phantoms/bids_test3
    /home/yoh/datalad/labs
    /home/yoh/datalad/labs/haxby
    /home/yoh/datalad/labs/haxby/raiders
    /home/yoh/datalad/openfmri
    /home/yoh/datalad/openfmri/ds000001
    ..    .

.. _OpenfMRI: http://openfmri.org
.. _CRCNS: http://crcns.org

Supported meta data formats
===========================

This following sections provide an overview of supported meta data formats.


RFC822-compliant meta data
--------------------------

This is a custom meta data format, inspired by the standard used for Debian
software packages that is particularly suited for manual entry. This format is
a good choice when meta data describing a dataset as a whole cannot be obtained
from some other structured format. The syntax is :rfc:`822`-compliant. In other
words: this is a text-based format that uses the syntax of email headers.
Meta data must be placed in ``DATASETROOT/.datalad/meta.rfc822`` for this format.

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


Brain Imaging Data Structure (BIDS)
-----------------------------------

DataLad has basic support for extraction of meta data from the `BIDS
<http://bids.neuroimaging.io>`_ ``dataset_description.json`` file.

Friction-less data packages
---------------------------

DataLad has basic support for extraction of meta data from `friction-less data
packages <http://specs.frictionlessdata.io/data-packages>`_
(``datapackage.json``).  file.

JSON-LD meta data format
------------------------

DataLad uses JSON-LD_ as its primary meta data format. By default, the
following context (available from `here <schema.json>`_
is used for any meta data item:

.. literalinclude:: _extras/schema.json
   :language: json

While it is technically possible to mix different contexts across items this
has not been fully tested yet.

The following sections describe details and changes in the meta data
specifications implemented in datalad.

.. _0.1:

v0.1
----

* Original implementation
