.. -*- mode: rst -*-
.. vi: set ft=rst sts=4 ts=4 sw=4 et tw=79:

.. _chap_design_application_vs_libary_mode:

***************************************
Application-type vs. library-type usage
***************************************

.. topic:: Specification scope and status

   This specification describes the current implementation.

Historically, DataLad was implemented with the assumption of application-type
usage, i.e., a person using DataLad through any of its APIs. Consequently,
(error) messaging was primarily targeting humans, and usage advice focused on
interactive use. With the increasing utilization of DataLad as an
infrastructural component it was necessary to address use cases of library-type
or internal usage more explicitly.

DataLad continues to behave like a stand-alone application by default.

For internal use, Python and command-line APIs provide dedicated mode switches.

The command line entry point offers a ``--library-mode`` switch that enables
the mode very early in the process runtime, and for the complete lifetime of the
process. Similarly, the Python API offers a function ``enable_libarymode()``
that should be called immediately after importing the ``datalad`` package
for maximum impact.

.. code-block:: python

   >>> import datalad
   >>> datalad.enable_libarymode()

Moreover, with ``datalad.in_librarymode()`` a query utility is provided that
can be used throughout the code base for adjusting behavior according to the
usage scenario.

Switching back and forth between modes during the runtime of a process is not
supported.

Care must be taken to configure child-processes of the main DataLad
process/session appropriately, for example internal Dataset procedure calls, in
order to inherit the mode of the parent process.


Library-mode implications
=========================

Once the mode distinction has actual behavioral consequences, such consequences
should be summarized here.
