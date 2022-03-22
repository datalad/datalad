import sys

from datalad.downloaders import (
    GitCredential,
    UserPassword,
)
from datalad.downloaders.providers import (
    AUTHENTICATION_TYPES,
    Providers,
)
from datalad.local.gitcredential import _credspec2dict
from datalad import ConfigManager

git_credential_datalad_help = """\
Git credential interface to DataLad's credential management system.

In order to use this, one needs to configure git to use the credential helper
'datalad'. In the simplest case this can be achieved by 'git config --add
--global credential.helper datalad'. This can be restricted to apply to
certain URLs only. See 'man gitcredentials' and
http://docs.datalad.org/credentials.html for details.

Only DataLad's UserPassword-type credentials are supported. This helper
passes standard 'get', 'store' actions on to the respective interfaces in
DataLad.
The 'erase' action is not supported, since this is called by Git, when the
credentials didn't work for a URL. However, DataLad's providers store a regex
for matching URLs. That regex-credential combo may still be valid and simply
too broad. We wouldn't want to auto-delete in that case. Another case is a
somewhat circular setup: Another credential-helper provided the credentials and
is also used by DataLad. The provider config connecting it to DataLad could be
intentionally broad. Deleting credentials from keyring but keeping the provider
config pointing to them, on the other hand,  would be even worse, as it would
invalidate the provider config and also means rejecting credentials w/o context.
Hence, this helper doesn't do anything on 'erase' at the moment.

usage: git credential-datalad [option] <action>

options:
    -h                   Show this help.

If DataLad's config variable 'datalad.credentials.githelper.noninteractive' is
set: Don't ask for user confirmation when storing to DataLad's credential
system. This may fail if default names result in a conflict with existing ones.
This mode is used for DataLad's CI tests. Note, that this config can not
reliably be read from local configs (a repository's .git/config or
.datalad/config) as this credential helper when called by Git doesn't get to
know what repository it is operating on.
"""


def git_credential_datalad():
    """Entrypoint to query DataLad's credentials via git-credential
    """

    if len(sys.argv) != 2 \
            or sys.argv[1] == "-h" \
            or sys.argv[1] not in ['get', 'store', 'erase']:
        help_explicit = sys.argv[1] == "-h"
        print(git_credential_datalad_help,
              file=sys.stdout if help_explicit else sys.stderr)
        sys.exit(0 if help_explicit else 1)

    cfg = ConfigManager()
    interactive = not cfg.obtain("datalad.credentials.githelper.noninteractive")
    action = sys.argv[-1]
    attrs = _credspec2dict(sys.stdin)

    # This helper is intended to be called by git. While git-credential takes a
    # `url` property of the description, what it passes on is `protocol`, `host`
    # and potentially `path` (if instructed to useHttpPath by config).
    # For communication with datalad's credential system, we need to reconstruct
    # the url, though.
    assert 'protocol' in attrs.keys()
    assert 'host' in attrs.keys()
    if 'url' not in attrs:
        attrs['url'] = "{protocol}://{host}{path}".format(
            protocol=attrs.get('protocol'),
            host=attrs.get('host'),
            path="/{}".format(attrs.get('path')) if 'path' in attrs else ""
        )

    # Get datalad's provider configs.
    providers = Providers.from_config_files()

    if action == 'get':
        _action_get(attrs, providers)
    elif action == 'store':
        _action_store(attrs, interactive, providers)


def _action_store(attrs, interactive, providers):
    # Determine the defaults to use for storing. In non-interactive mode,
    # this is what's going to be stored, in interactive mode user is
    # presented with them as default choice.
    # We don't really know what authentication type makes sense to store in
    # the provider config (this would be relevant for datalad using those
    # credentials w/o git).
    # However, pick 'http_basic_auth' in case of HTTP(S) URL and 'none'
    # otherwise as the default to pass into store routine.
    if attrs.get('protocol') in ['http', 'https']:
        authentication_type = 'http_basic_auth'
    else:
        authentication_type = 'none'
    # If we got a `path` component from git, usehttppath is set and thereby
    # git was instructed to include it when matching. Hence, do the same.
    url_re = "{pr}://{h}{p}.*".format(pr=attrs.get('protocol'),
                                      h=attrs.get('host'),
                                      p="/" + attrs.get('path')
                                      if "path" in attrs.keys() else "")
    name = attrs.get('host')
    credential_name = name
    credential_type = "user_password"
    if not interactive:

        # TODO: What about credential labels? This could already exist as
        #       well. However, it's unlikely since the respective
        #       "service name" for keyring is prepended with "datalad-".
        #       For the same reason of how the keyring system is used by
        #       datalad it's not very transparently accessible what labels
        #       we'd need to check for. Rather than encoding knowledge about
        #       datalad's internal handling here, let's address that in
        #       datalad's provider and credential classes and have an easy
        #       check to be called from here.
        if any(p.name == name for p in providers):
            print(f"Provider name '{name}' already exists. This can't be "
                  "resolved in non-interactive mode.",
                  file=sys.stderr)

        authenticator_class = AUTHENTICATION_TYPES[authentication_type]
        saved_provider = providers._store_new(
            url=attrs.get('url'),
            authentication_type=authentication_type,
            authenticator_class=authenticator_class,
            url_re=url_re,
            name=name,
            credential_name=credential_name,
            credential_type=credential_type,
            level='user'
        )
    else:
        # use backend made for annex special remotes for interaction from a
        # subprocess whose stdin/stdout are in use for communication with
        # its parent
        from datalad.ui import ui
        ui.set_backend('annex')

        # ensure default is first in list (that's how `enter_new` determines
        # it's the default)
        auth_list = AUTHENTICATION_TYPES.copy()
        auth_list.pop(authentication_type, None)
        auth_list = [authentication_type] + list(auth_list.keys())

        saved_provider = providers.enter_new(
            url=attrs.get('url'),
            auth_types=auth_list,
            url_re=url_re,
            name=name,
            credential_name=credential_name,
            credential_type=credential_type)
    saved_provider.credential.set(user=attrs['username'],
                                  password=attrs['password'])


def _action_get(attrs, providers):
    # query datalad and report if it knows anything, or be silent
    # git handles the rest
    provider = providers.get_provider(attrs['url'],
                                      only_nondefault=True)
    if provider is None \
            or provider.credential is None \
            or not isinstance(provider.credential, UserPassword):
        # datalad doesn't know or only has a non UserPassword credential for
        # this URL - create empty entry
        dlcred = UserPassword()
    else:
        dlcred = provider.credential
        # Safeguard against circular querying. We are a git-credential-helper.
        # If we find a datalad credential that tells DataLad to query Git, we
        # need to ignore it. Otherwise we'd end up right here again.
        if isinstance(provider.credential, GitCredential):
            # Just return the unchanged description we got from Git
            for k, v in attrs.items():
                print('{}={}'.format(k, v))
            return

    for dlk, gitk in (('user', 'username'), ('password', 'password')):
        val = dlcred.get(dlk)
        if val is not None:
            print('{}={}'.format(gitk, val))
