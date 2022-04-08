.. -*- mode: rst -*-
.. vi: set ft=rst sts=4 ts=4 sw=4 et tw=79:

.. _chap_design_docstrings:

**********
Docstrings
**********

.. topic:: Specification scope and status

   This specification provides a partial overview of the current
   implementation.

Docstrings in DataLad source code are used and consumed in many ways. Besides
serving as documentation directly in the sources, they are also transformed
and rendered in various ways.

- Command line ``--help`` output
- Python's ``help()`` or IPython's ``?``
- Manpages
- Sphinx-rendered documentation for the Python API and the command line API

A common source docstring is transformed, amended and tuned specifically for
each consumption scenario.


Formatting overview and guidelines
==================================

Version information
-------------------

Additions, changes, or deprecation should be recorded in a docstring using the
standard Sphinx directives ``versionadded``, ``versionchanged``,
``deprecated``::

  .. deprecated:: 0.16
     The ``dryrun||--dryrun`` option will be removed in a future release, use
     the renamed ``dry_run||--dry-run`` option instead.


API-conditional docs
--------------------

The ``CMD`` and ``PY`` macros can be used to selectively include documentation
for specific APIs only::

  options to pass to :command:`git init`. [PY: Options can be given as a list
  of command line arguments or as a GitPython-style option dictionary PY][CMD:
  Any argument specified after the destination path of the repository will be
  passed to git-init as-is CMD].

For API-alternative command and argument specifications the following format
can be used::

  ``<python-api>||<cmdline-api``

where the double backticks are mandatory and ``<python-part>`` and
``<cmdline-part>`` represent the respective argument specification for each
API. In these specifications only valid argument/command names are allowed,
plus a comma character to list multiples, and the dot character to include an
ellipsis::

   ``github_organization||-g,--github-organization``

   ``create_sibling_...||create-sibling-...``


Reflow text
-----------

When automatic transformations negatively affect the presentation of a
docstring due to excessive removal of content, leaving "holes", the ``REFLOW``
macro can be used to enclose such segments, in order to reformat them
as the final processing step. Example::

  || REFLOW >>
  The API has been aligned with the some
  ``create_sibling_...||create-sibling-...`` commands of other GitHub-like
  services, such as GOGS, GIN, GitTea.<< REFLOW ||

The start macro must appear on a dedicated line.
