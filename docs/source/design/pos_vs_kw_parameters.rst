.. -*- mode: rst -*-
.. vi: set ft=rst sts=4 ts=4 sw=4 et tw=79:

.. _chap_pos_vs_kw_parameters:

********************************
Positional vs Keyword parameters
********************************

.. topic:: Specification scope and status

   This specification is a proposal, subject to review and further discussion.
   Technical preview was implemented in the `PR #6176 <https://github.com/datalad/datalad/pull/6176>`_.

Motivation
==========

Python allows for keyword arguments (arguments with default values) to be specified positionally.
That complicates addition or removal of new keyword arguments since such changes must account for their possible
positional use.
Moreover, in case of our Interface's, it contributes to inhomogeneity since when used in :term:`CLI`, all keyword
arguments
must be specified via non-positional ``--<option>``'s, whenever Python interface allows for them to be used
positionally.

Python 3 added possibility to use a ``*`` separator in the function definition to mandate that all keyword arguments
*after* it must be be used only via keyword (``<option>=<value>``) specification.
It is encouraged to use ``*`` to explicitly separate out positional from keyword arguments in majority of the cases,
and below we outline two major types of constructs.

Interfaces
==========

Subclasses of the :class:`~datalad.interface.base.Interface` provide specification and implementation for both
:term:`CLI` and Python API interfaces.
All new interfaces must separate all CLI ``--options`` from positional arguments using ``*`` in their ``__call__``
signature.

**Note:** that some positional arguments could still be optional (e.g., destination ``path`` for ``clone``),
and thus should be listed **before** ``*``, despite been defined as a keyword argument in the ``__call__`` signature.

A unit-test will be provided to guarantee such consistency between :term:`CLI` and Python interfaces.
Overall, exceptions to this rule could be only some old(er) interfaces.

Regular functions and methods
=============================

Use of ``*`` is encouraged for any function (or method) with keyword arguments.
Generally, ``*`` should come before the first keyword argument, but similarly to the Interfaces above, it is left to
the discretion of the developer to possibly allocate some (just few) arguments which could be used positionally if
specified.