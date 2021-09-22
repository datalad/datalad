.. -*- mode: rst -*-
.. vi: set ft=rst sts=4 ts=4 sw=4 et tw=79:

.. _chap_design_credentials:

*********************
Credential management
*********************

.. topic:: Specification scope and status

   This specification describes the current implementation.

Various components of DataLad need to be passed credentials to interact with services that require authentication. 
This includes downloading files, but also things like REST API usage.

Supported credential types include basic user/password combinations, access tokens, and a range of tailored solutions for particular services.
All credential type implementations are derived from a common :class:`Credential` base class.

Importantly, credentials must be identified by a name.
This name is a label that is often hard-coded in the program code of DataLad, any of its extensions, or specified in a dataset.

Given a credential ``name``, one or more credential ``component``\(s) (e.g., ``token``, ``username``, or ``password``) can be looked up by DataLad in at least two different locations.
These locations are tried in the following order, and the first successful lookup yields the final value.

1. A configuration item ``datalad.credential.<name>.<component>``.
   Such configuration items can be defined in any location supported by DataLad's configuration system.
   As with any other specification of configuration items, environment variables can be used to set or override credentials.
   Variable names take the form of ``DATALAD_CREDENTIAL_<NAME>_<COMPONENT>``, and standard replacement rules into configuration variable names apply.

2. DataLad uses the `keyring` package https://pypi.org/project/keyring to connect to any of its supported back-ends for setting or getting credentials.
   This provides support for credential storage on all major platforms, but also extensibility, providing 3rd-parties to implement and use specialized solutions.

When a credential is required for operation, but could not be obtained via any of the above approaches, DataLad can prompt for credentials in interactive terminal sessions.
Interactively entered credentials will be stored in the active credential store available via the ``keyring`` package.

When a credential value is known but invalid, the invalid value must be removed or replaced in the active credential store.
By setting the configuration flag ``datalad.credentials.force-ask``, DataLad can be instructed to force interactive credential re-entry to effectively override any store credential with a new value.
