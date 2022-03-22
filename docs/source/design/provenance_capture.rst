.. -*- mode: rst -*-
.. vi: set ft=rst sts=4 ts=4 sw=4 et tw=79:

.. _chap_design_provenance_capture:

******************
Provenance capture
******************

.. topic:: Specification scope and status

   This specification describes the current implementation.

The ability to capture process provenance---the information what activity
initiated by which entity yielded which outputs, given a set of parameters, a
computational environment, and potential input data---is a core feature of
DataLad.

Provenance capture is supported for any computational process that can be
expressed as a command line call. The simplest form of provenance tracking can
be implemented by prefixing any such a command line call with ``datalad run
...``.  When executed in the content of a dataset (with the current working
directory typically being in the root of a dataset), DataLad will then:

1. check the dataset for any unsaved modifications
2. execute the given command, when no modifications were found
3. save any changes to the dataset that exist after the command has exited without error

The saved changes are annotated with a structured record that, at minimum,
contains the executed command.

This kind of usage is sufficient for building up an annotated history of a
dataset, where all relevant modifications are clearly associated with the
commands that caused them. By providing more, optional, information to the
``run`` command, such as a declaration of inputs and outputs, provenance
records can be further enriched. This enables additional functionality, such as
the automated re-execution of captured processes.


The provenance record
=====================

A DataLad provenance record is a key-value mapping comprising the following
main items:

- ``cmd``: executed command, which may contain placeholders
- ``dsid``: DataLad ID of dataset in whose context the command execution took place
- ``exit``: numeric exit code of the command
- ``inputs``: a list of (relative) file paths for all declared inputs
- ``outputs``: a list of (relative) file paths for all declared outputs
- ``pwd``: relative path of the working directory for the command execution

A provenance record is stored in a JSON-serialized form in one of two locations:

1. In the body of the commit message created when saving caused the dataset modifications
2. In a sidecar file underneath ``.datalad/runinfo`` in the root dataset

Sidecar files have a filename (``record_id``) that is based on checksum of the
provenance record content, and are stored as LZMA-compressed binary files.
When a sidecar file is used, its ``record_id`` is added to the commit message,
instead of the complete record.


Declaration of inputs and outputs
=================================

While not strictly required, it is possible and recommended to declare all
paths for process inputs and outputs of a command execution via the respective
options of ``run``.

For all declared inputs, ``run`` will ensure that their file content is present
locally at the required version before executing the command.

For all declared outputs, ``run`` will ensure that the respective locations are
writeable.

It is recommended to declare inputs and outputs both exhaustively and precise,
in order to enable the provenance-based automated re-execution of a command. In
case of a future re-execution the dataset content may have changed
substantially, and a needlessly broad specification of inputs/outputs may lead
to undesirable data transfers.


Placeholders in commands and IO specifications
==============================================

Both command and input/output specification can employ placeholders that will
be expanded before command execution. Placeholders use the syntax of the Python
``format()`` specification. A number of standard placeholders are supported
(see the ``run`` documentation for a complete list):

- ``{pwd}`` will be replaced with the full path of the current working directory
- ``{dspath}`` will be replaced with the full path of the dataset that run is invoked on
- ``{inputs}`` and ``{outputs}`` expand a space-separated list of the declared input and output paths

Additionally, custom placeholders can be defined as configuration variables
under the prefix ``datalad.run.substitutions.``. For example, a configuration
setting ``datalad.run.substitutions.myfile=data.txt`` will cause the
placeholder ``{myfile}`` to expand to ``data.txt``.

Selection of individual items for placeholders that expand to multiple values
is possible via the standard Python ``format()`` syntax, for example
``{inputs[0]}``.


Result records emitted by ``run``
=================================

When performing a command execution ``run`` will emit results for:

1. Input preparation (i.e. downloads)
2. Output preparation (i.e. unlocks and removals)
3. Command execution
4. Dataset modification saving (i.e. additions, deletions, modifications)

By default, ``run`` will stop on the first error. This means that, for example,
any failure to download content will prevent command execution. A failing
command will prevent saving a potential dataset modification. This behavior can
be altered using the standard ``on_failure`` switch of the ``run`` command.

The emitted result for the command execution contains the provenance record
under the ``run_info`` key.


Implementation details
======================

Most of the described functionality is implemented by the function
:func:`datalad.core.local.run.run_command`. It is interfaced by the ``run``
command, but also ``rerun``, a utility for automated re-execution based on
provenance records, and ``containers-run`` (provided by the ``container``
extension package) for command execution in DataLad-tracked containerized
environments. This function has a more complex interface, and supports a wider
range of use cases than described here.
