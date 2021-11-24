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

Library mode can be enabled by setting the boolean configuration setting
``datalad.runtime.librarymode`` **before the start of the DataLad process**.
From the command line, this can be done with the option
``-c datalad.runtime.librarymode=yes``, or any other means for setting
configuration. In an already running Python process, library mode can be
enabled by calling ``datalad.enable_libarymode()``. This should be done
immediately after importing the ``datalad`` package for maximum impact.

.. code-block:: python

   >>> import datalad
   >>> datalad.enable_libarymode()

In a Python session, library mode **cannot** be enabled reliably by just setting
the configuration flag **after** the ``datalad`` package was already imported.
The ``enable_librarymode()`` function must be used.

Moreover, with ``datalad.in_librarymode()`` a query utility is provided that
can be used throughout the code base for adjusting behavior according to the
usage scenario.

Switching back and forth between modes during the runtime of a process is not
supported.

A library mode setting is exported into the environment of the Python process.
By default, it will be inherited by all child-processes, such as dataset
procedure executions.


Library-mode implications
=========================

No Python API docs
  Generation of comprehensive doc-strings for all API commands is skipped. This
  speeds up ``import datalad.api`` by about 30%.
