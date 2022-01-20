Credentials
***********

Integration with Git
====================

Git and DataLad can use each other's credential system.
In order to allow Git to query credentials from DataLad, the git credential helper delivered with DataLad needs to be configured.
That is, a section like this needs to be part of one's git config file::

  [credential "https://*.data.example.com"]
    helper = "datalad"

Note:

- This most likely only makes sense at the user or system level (options `--global`|`--system` with `git config`), since cloning of a repository needs the credentials before there is a local repository.
- The name of that section is a URL matching expression - see `man gitcredentials`.
- The URL matching does NOT include the scheme! Hence, if you need to match `http` as well as `https`, you need two such entries.
- Multiple different git credential helpers can be configured - Git will ask them one after another. For example on OSX, Git comes with a helper to use the OSX keychain which is configured at system level. This does not conflict with setting up DataLad's credential helper.

The other way around, DataLad can ask Git for credentials it knows by other means (other git credential helpers).
For that a datalad provider config needs to be set up in similar fashion::

  [provider:data_example_provider]
    url_re = http.*://.*data\.example\.com
    authentication_type = http_basic_auth
    credential = data_example_cred
  [credential:data_example_cred]
    type = git

Such a config lives in a dedicated file named after the provider name (:file:`data_example_provider.cfg` in this case).
Valid locations for these files are listed in :ref:`chap_design_credentials`.
In opposition to Git's approach, `url_re` is a regular expression that matches the entire URL including the scheme.
The name of the provider section (`data_example_provider`)needs to match the file name.
The name of the credential section (`data_example_cred`) needs to match the `credential` entry in the provider section.

DataLad will create a provider configuration interactively, whenever it first encounters an URL that requires authentication and no credentials can be matched yet.
This behavior extends to the git credential helper and can therefore even be triggered by a `git clone`.
However, `git-credential-datalad` will not do this, if the config variable `datalad.credentials.githelper.noninteractive` is set.
