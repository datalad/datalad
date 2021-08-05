.. -*- mode: rst -*-
.. vi: set ft=rst sts=4 ts=4 sw=4 et tw=79:

.. _chap_design_log_levels:

**********
Log levels
**********

.. topic:: Specification scope and status

   This specification provides a partial overview of the current
   implementation.


Log messages are emitted by a wide range of operations within DataLad. They are
categorized into distinct levels. While some levels have self-explanatory
descriptions (e.g. ``warning``, ``error``), others are less specific (e.g.
``info``, ``debug``).

Common principles
=================

Parenthical log message use the same level
  When log messages are used to indicate the start and end of an operation,
  both start and end message use the same log-level.

Use cases
=========

Command execution
-----------------

For the :class:`~datalad.cmd.WitlessRunner` and its protocols the following log levels are used:

- High-level execution -> ``debug``
- Process start/finish -> ``8``
- Threading and IO -> ``5``
