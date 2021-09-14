.. -*- mode: rst -*-
.. vi: set ft=rst sts=4 ts=4 sw=4 et tw=79:

.. _chap_design_dataset_argument:

********************
``dataset`` argument
********************

.. topic:: Specification scope and status

   This specification describes the current implementation.

All commands which operate on datasets have a ``dataset`` argument (``-d`` or
``--dataset`` for the :term:`CLI`) to identify a single dataset as the
context of an operation.
If ``--dataset`` argument is not provided, the context of an operation is command-specific.
For example, `clone` command will consider the :term:`dataset` which is being cloned to be the context.
But typically, a dataset which current working directory belongs to is the context of an operation.
In the latter case, if operation (e.g., `get`) does not find a dataset in current working directory, operation fails with an ``NoDatasetFound`` error.


Impact on relative path resolution
==================================

With one exception, the nature of a provided ``dataset`` argument does **not**
impact the interpretation of relative paths. Relative paths are always considered
to be relative to the process working directory.

The one exception to this rule is passing a ``Dataset`` object instance as
``dataset`` argument value in the Python API. In this, and only this, case, a
relative path is interpreted as relative to the root of the respective dataset.


Special values
==============

There are some pre-defined "shortcut" values for dataset arguments:

``^``
   Represents to the topmost superdataset that contains the dataset the current
   directory is part of.
``^.``
   Represents the root directory of the dataset the current directory is part of.
``///``
   Represents the "default" dataset located under `$HOME/datalad/`.


Use cases
=========

Save modification in superdataset hierarchy
-------------------------------------------

Sometimes it is convenient to work only in the context of a subdataset.
Executing a ``datalad save <subdataset content>`` will record changes to the
subdataset, but will leave existing superdatasets dirty, as the subdataset
state change will not be saved there. Using the ``dataset`` argument it is
possible to redefine the scope of the save operation. For example::

  datalad save -d^ <subdataset content>

will perform the exact same save operation in the subdataset, but additionally
save all subdataset state changes in all superdatasets until the root of a
dataset hierarchy. Except for the specification of the dataset scope there is
no need to adjust path arguments or change the working directory.
