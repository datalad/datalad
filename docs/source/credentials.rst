Credentials
***********

Integration with Git
====================

Git and DataLad can use each other's credential system.
Both directions are independent of each other and none is necessarily required.
Either direction can be configured based on URL matching patterns.
In addition, Git can be configured to always query DataLad for credentials without any URL matching.

Let Git query Datalad
=====================

In order to allow Git to query credentials from DataLad, Git needs to be configured to use the git credential helper delivered with DataLad (an executable called `git-credential-datalad`).
That is, a section like this needs to be part of one's git config file::

  [credential "https://*.data.example.com"]
    helper = "datalad"

Note:

- This most likely only makes sense at the user or system level (options `--global`|`--system` with `git config`), since cloning of a repository needs the credentials before there is a local repository.
- The name of that section is a URL matching expression - see `man gitcredentials`.
- The URL matching does NOT include the scheme! Hence, if you need to match `http` as well as `https`, you need two such entries.
- Multiple git credential helpers can be configured - Git will ask them one after another until it got a username and a password for the URL in question. For example on macOS, Git comes with a helper to use the system's keychain and Git is configured system-wide to query `git-credential-osxkeychain`. This does not conflict with setting up DataLad's credential helper.
- The example configuration requires `git-credential-datalad` to be in the path in order for Git to find it. Alternatively, the value of the `helper` entry needs to be the absolute path of `git-credential-datalad`.
- In order to make Git always consider DataLad as a credential source, one can simply not specify any URL pattern (so it's `[credential]` instead of `[credential "SOME-PATTERN"]`)

Let DataLad query Git
=====================

The other way around, DataLad can ask Git for credentials (which it will acquire via other git credential helpers).
To do so, a DataLad provider config needs to be set up::

  [provider:data_example_provider]
    url_re = https://.*data\.example\.com
    authentication_type = http_basic_auth
    credential = data_example_cred
  [credential:data_example_cred]
    type = git

Note:

- Such a config lives in a dedicated file named after the provider name (e.g. all of the above example would be the content of :file:`data_example_provider.cfg`, matching `[provider:data_example_provider]`).
- Valid locations for these files are listed in :ref:`chap_design_credentials`.
- In opposition to Git's approach, `url_re` is a regular expression that matches the entire URL including the scheme.
- The above is particularly important in case of redirects, as DataLad currently matches the URL it was given instead of the one it ultimately uses the credentials with.
- The name of the credential section must match the credential entry in the provider section (e.g. `[credential:data_example_cred]` and `credential = data_example_cred` in the above example).

DataLad will prompt the user to create a provider configuration and respective credentials when it first encounters a URL that requires authentication but no matching credentials are found.
This behavior extends to the credential helper and may therefore be triggered by a `git clone` if Git is configured to use `git-credential-datalad`.
However, interactivity of `git-credential-datalad` can be turned off (see `git-credential-datalad -h`)

It is possible to end up in a situation where Git would query DataLad and vice versa for the same URL, especially if Git is configured to query DataLad unconditionally.
`git-credential-datalad` will discover this circular setup and stop it by simply ignoring DataLad's provider configuration that points back to Git.
