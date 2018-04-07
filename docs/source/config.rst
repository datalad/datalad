Configuration
*************

DataLad uses the same configuration mechanism and syntax as Git itself.
Consequently, datalad can be configured using the :command:`git config`
command. Both a *global* user configuration (typically at
:file:`~/.gitconfig`), and a *local* repository-specific configuration
(:file:`.git/config`) are inspected.

In addition, datalad supports a persistent dataset-specific configuration.
This configuration is stored at :file:`.datalad/config` in any dataset.  As it
is part of a dataset, settings stored there will also be in effect for any
consumer of such a dataset. Both *global* and *local* settings on a particular
machine always override configuration shipped with a dataset.

All datalad-specific configuration variables are prefixed with ``datalad.``.

It is possible to override or amend the configuration using environment
variables. Any variable with a name that starts with ``DATALAD_`` will
be available as the corresponding ``datalad.`` configuration variable,
replacing any ``__`` (two underscores) with a hyphen, then any ``_``
(single underscore) with a dot, and finally converting all letters to
lower case. Values from environment variables take precedence over
configuration file settings.

The following sections provide a (non-exhaustive) list of settings honored
by datalad. They are categorized according to the scope they are typically
associated with.


Global user configuration
=========================

.. include:: generated/cfginfo/global.rst

Local repository configuration
==============================

.. include:: generated/cfginfo/local.rst

Sticky dataset configuration
=============================

.. include:: generated/cfginfo/dataset.rst

Miscellaneous configuration
===========================

.. include:: generated/cfginfo/misc.rst
