.. -*- mode: rst -*-
.. vi: set ft=rst sts=4 ts=4 sw=4 et tw=79:

.. _chap_design_credentials:

*********************
Credential management
*********************

.. topic:: Specification scope and status

   This specification describes the current implementation.

Various components of DataLad need to be passed credentials to interact with services that require authentication. 
This includes downloading files, but also things like REST API usage or authenticated cloning.
Key components of Datalad's credential management are credentials types, providers, authenticators and downloaders.

Credentials
===========

Supported credential types include basic user/password combinations, access tokens, and a range of tailored solutions for particular services.
All credential type implementations are derived from a common :class:`Credential` base class.
A mapping from string labels to credential classes is defined in ``datalad.downloaders.CREDENTIAL_TYPES``.

Importantly, credentials must be identified by a name.
This name is a label that is often hard-coded in the program code of DataLad, any of its extensions, or specified in a dataset or in provider configurations (see below).

Given a credential ``name``, one or more credential ``component``\(s) (e.g., ``token``, ``username``, or ``password``) can be looked up by DataLad in at least two different locations.
These locations are tried in the following order, and the first successful lookup yields the final value.

1. A configuration item ``datalad.credential.<name>.<component>``.
   Such configuration items can be defined in any location supported by DataLad's configuration system.
   As with any other specification of configuration items, environment variables can be used to set or override credentials.
   Variable names take the form of ``DATALAD_CREDENTIAL_<NAME>_<COMPONENT>``, and standard replacement rules into configuration variable names apply.

2. DataLad uses the `keyring` package https://pypi.org/project/keyring to connect to any of its supported back-ends for setting or getting credentials,
   via a wrapper in :mod:`~datalad.support.keyring_`.
   This provides support for credential storage on all major platforms, but also extensibility, providing 3rd-parties to implement and use specialized solutions.

When a credential is required for operation, but could not be obtained via any of the above approaches, DataLad can prompt for credentials in interactive terminal sessions.
Interactively entered credentials will be stored in the active credential store available via the ``keyring`` package.
Note, however, that the keyring approach is somewhat abused by datalad.
The wrapper only uses ``get_/set_password`` of ``keyring`` with the credential's ``FIELDS`` as the name to query (essentially turning the keyring into a plain key-value store) and "datalad-<CREDENTIAL-LABEL>" as the "service name".
With this approach it's not possible to use credentials in a system's keyring that were defined by other, datalad unaware software (or users).

When a credential value is known but invalid, the invalid value must be removed or replaced in the active credential store.
By setting the configuration flag ``datalad.credentials.force-ask``, DataLad can be instructed to force interactive credential re-entry to effectively override any store credential with a new value.

Providers
=========

Providers are associating credentials with a context for using them and are defined by configuration files.
A single provider is represented by :class:`Provider` object and the list of available providers is represented by the :class:`Providers` class.
A provider is identified by a label and stored in a dedicated config file per provider named `LABEL.cfg`.
Such a file can reside in a dataset (under `.datalad/providers/`), at the user level (under `{user_config_dir}/providers`), at the system level (under `{site_config_dir}/providers`) or come packaged with the datalad distribution (in directory `configs` next to `providers.py`).
Such a provider specifies a regular expression to match URLs against and assigns authenticator abd credentials to be used for a match.
Credentials are referenced by their label, which in turn is the name of another section in such a file specifying the type of the credential.
References to credential and authenticator types are strings that are mapped to classes by the following dict definitions:

- ``datalad.downloaders.AUTHENTICATION_TYPES``
- ``datalad.downloaders.CREDENTIAL_TYPES``

Available providers can be loaded by ``Providers.from_config_files`` and ``Providers.get_provider(url)`` will match a given URL against them and return the appropriate `Provider` instance.
A :class:`Provider` object will determine a downloader to use (derived from :class:`BaseDownloader`), based on the URL's protocol.

Note, that the provider config files are not currently following datalad's general config approach.
Instead they are special config files, read by :class:`configparser.ConfigParser` that are not compatible with `git-config` and hence the :class:`ConfigManager`.

There are currently two ways of storing a provider and thus creating its config file: ``Providers.enter_new`` and ``Providers._store_new``.
The former will only work interactively and provide the user with options to choose from, while the latter is non-interactive and can therefore only be used, when all properties of the provider config are known and passed to it.
There's no way at the moment to store an existing :class:`Provider` object directly.

Integration with Git
====================

In addition, there's a special case for interfacing `git-credential`: A dedicated :class:`GitCredential` class is used to talk to Git's ``git-credential`` command instead of the keyring wrapper.
This class has identical fields to the :class:`UserPassword` class and thus can be used by the same authenticators.
Since Git's way to deal with credentials doesn't involve labels but only matching URLs, it is - in some sense - the equivalent of datalad's provider layer.
However, providers don't talk to a backend, credentials do.
Hence, a more seamless integration requires some changes in the design of datalad's credential system as a whole.

In the opposite direction - making Git aware of datalad's credentials, there's no special casing, though.
Datalad comes with a `git-credential-datalad` executable.
Whenever Git is configured to use it by setting `credential.helper=datalad`, it will be able to query datalad's credential system for a provider matching the URL in question and retrieve the referenced by this provider credentials.
This helper can also store a new provider+credentials when asked to do so by Git.
It can do this interactively, asking a user to confirm/change that config or - if `credential.helper='datalad --non-interactive'` - try to non-interactively store with its defaults.

Authenticators
==============

Authenticators are used by downloaders to issue authenticated requests.
They are not easily available to directly be applied to requests being made outside of the downloaders.
