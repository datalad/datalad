.. -*- mode: rst -*-
.. vi: set ft=rst sts=4 ts=4 sw=4 et tw=79:

.. _chap_standard_parameters:

*******************
Standard parameters
*******************

.. topic:: Specification scope and status

   This specification partially describes the current implementation, and partially is a proposal, subject to review and further discussion.

Several "standard parameters" are used in various DataLad commands.
Those standard parameters have an identical meaning across the commands they are used in.
Commands should ensure that they use those "standard parameters" where applicable and do not deviate from the common names nor the common meaning.

Currently used standard parameters are listed below, as well as suggestions on how to harmonize currently deviating standard parameters.
Deviations from the agreed upon list should be harmonized.
The parameters are listed in their command-line form, but similar names and descriptions apply to their Python form.

``-d``/``--dataset``
  A pointer to the dataset that a given command should operate on

``--dry-run``
  Display details about the command execution without actually running the command.

``-f``/``--force``
  Enforce the execution of a command, even when certain security checks would normally prevent this

``-J``/``--jobs``
  Number of parallel jobs to use.

``-m``/``--message``
  A commit message to attach to the saved change of a command execution.

``-r``/``--recursive``
  Perform an operation recursively across subdatasets

``-R``/``--recursion-limit``
  Limit recursion to a given amount of subdataset levels

``-s``/``--sibling-name`` [SUGGESTION]
  The identifier for a dataset sibling (remote)


Certain standard parameters will have their own design document.
Please refer to those documents for more in-depth information.