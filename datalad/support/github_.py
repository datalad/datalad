# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Helpers for interaction with GitHub
"""
from .. import cfg
from ..consts import CONFIG_HUB_TOKEN_FIELD
from ..dochelpers import exc_str
from ..downloaders.credentials import UserPassword
from ..ui import ui
from ..utils import unique, assure_list, assure_tuple_or_list

from .exceptions import (
    AccessDeniedError,
    MissingExternalDependency,
)
from .network import URL

import logging
lgr = logging.getLogger('datalad.support.github_')

try:
    import github as gh
except ImportError:
    raise MissingExternalDependency(
        'PyGitHub',
        msg='GitHub-related functionality is unavailable without this package')


def get_repo_url(repo, access_protocol, github_login):
    """Report the repository access URL for Git matching the protocol"""
    prop = {
        'https': repo.clone_url,
        'ssh': repo.ssh_url
    }[access_protocol]
    if access_protocol == 'https' and github_login:
        # we were provided explicit github login.  For ssh access it is
        # impossible to specify different login within ssh RI, but it is
        # possible to do so for https logins
        url = URL(prop)
        assert url.scheme in ('http', 'https')
        url.username = github_login
        prop = url.as_str()
    return prop


def _token_str(token):
    """Shorten token so we do not leak sensitive info into the logs"""
    return token[:3] + '...' + token[-3:]


def _get_tokens_for_login(login, tokens):
    selected_tokens = []
    for t in tokens:
        try:
            g = gh.Github(t)
            gu = g.get_user()
            if gu.login == login:
                selected_tokens.append(t)
        except gh.BadCredentialsException as exc:
            lgr.debug(
                "Token %s caused %s while trying to check token's use"
                " login name. Skipping", _token_str(t), exc_str(exc))
    lgr.debug(
        "Selected %d tokens out of %d for the login %s",
        len(selected_tokens), len(tokens), login
    )
    return selected_tokens


def _gen_github_ses(github_login, github_passwd):
    """Generate viable Github sessions

    The idea is that we keep trying "new" ways to authenticate until we either
    exhaust or external loop stops asking for more

    Parameters
    ----------
    github_login:
    github_passwd:

    Yields
    -------
    Github, credential
      credential might be None if there is no credential associated as when
      we consider tokens from the config (instead of credentials store)

    """
    if github_login == 'disabledloginfortesting':
        raise gh.BadCredentialsException(403, 'no login specified')

    # see if we have tokens - might be many. Doesn't cost us much so get at once
    all_tokens = tokens = unique(
        assure_list(cfg.get(CONFIG_HUB_TOKEN_FIELD, None)),
        reverse=True
    )

    if not (github_login and github_passwd):
        # we don't have both
        # Check the tokens.  If login is provided, only the token(s) for the
        # login are considered. We consider oauth tokens as stored/used by
        # https://github.com/sociomantic/git-hub

        if github_login and tokens:
            # Take only the tokens which are Ok and correspond to that login
            tokens = _get_tokens_for_login(github_login, tokens)

        for token in tokens:
            try:
                yield(gh.Github(token), None)
            except gh.BadCredentialsException as exc:
                lgr.debug("Failed to obtain Github session for token %s",
                          _token_str(token))

    # We got here so time to try credentials

    # make it per user if github_login was provided. People might want to use
    # different credentials etc
    cred_identity = "%s@github" % github_login if github_login else "github"

    # if login and passwd were provided - try that one first
    try_creds = github_login and github_passwd
    try_login = bool(github_login)

    while True:
        if try_creds:
            # So we do not store them into cred store and thus do not need to
            # remove
            cred = None
            ses = gh.Github(github_login, password=github_passwd)
            user_name = github_login
            try_creds = None
        else:
            cred = UserPassword(cred_identity, 'https://github.com/login')
            # if github_login was provided, we should first try it as is,
            # and only ask for password
            if not cred.is_known:
                creds = {'user': github_login} if try_login else {}
                cred.enter_new(**creds)
            try_login = None
            creds = cred()
            user_name = creds['user']
            ses = gh.Github(user_name, password=creds['password'])
        # Get user and list its authorizations to verify that we do
        # not need 2FA
        user = ses.get_user()
        try:
            user_name_ = user.name  # should trigger need for 2FA
            # authorizations = list(user.get_authorizations())
            yield ses, cred
        except gh.BadCredentialsException as exc:
            lgr.error("Bad Github credentials")
        except (gh.TwoFactorException, gh.GithubException) as exc:
            # With github 1.43.5, in comparison to 1.40 we get a "regular"
            # GithubException for some reason, yet to check/report upstream
            # so we will just check for the expected in such cases messages
            if not (
                isinstance(exc, gh.GithubException) and
                getattr(exc, 'data', {}).get('message', '').startswith(
                    'Must specify two-factor authentication OTP code')
            ):
                raise

            # 2FA - we need to interact!
            if not ui.is_interactive:
                # Or should we just allow to pass
                raise RuntimeError(
                    "Cannot proceed with 2FA for Github - UI is not interactive. "
                    "Please 'manually' establish token based authentication "
                    "with Github and specify it in  %s  config"
                    % CONFIG_HUB_TOKEN_FIELD
                )
            if not ui.yesno(
                title="GitHub credentials - %s uses 2FA" % user_name,
                text="Generate a GitHub token to proceed? "
                     "If you already have a token for the account, "
                     "just say 'no' now and specify it in config (%s), "
                     "otherwise say 'yes' "
                    % (CONFIG_HUB_TOKEN_FIELD,)
                ):
                return

            token = _get_2fa_token(user)
            yield gh.Github(token), None  # None for cred so does not get killed

        # if we are getting here, it means we are asked for more and thus
        # aforementioned one didn't work out :-/
        if ui.is_interactive:
            if cred is not None:
                if ui.yesno(
                    title="GitHub credentials",
                    text="Do you want to try (re)entering GitHub credentials?"
                ):
                    cred.enter_new()
                else:
                    break
        else:
            # Nothing we could do
            lgr.debug(
                "UI is not interactive - we cannot query for more credentials"
            )
            break


def _get_2fa_token(user):
    one_time_password = ui.question(
        "2FA one time password", hidden=True, repeat=False
    )
    token_note = cfg.obtain('datalad.github.token-note')
    try:
        # TODO: can fail if already exists -- handle!?
        # in principle there is .authorization.delete()
        auth = user.create_authorization(
            scopes=['user', 'repo'],  # TODO: Configurable??
            note=token_note,  # TODO: Configurable??
            onetime_password=one_time_password)
    except gh.GithubException as exc:
        if (exc.status == 422  # "Unprocessable Entity"
                and exc.data.get('errors', [{}])[0].get('code') == 'already_exists'
        ):
            raise ValueError(
                "Token %r already exists. If you specified "
                "password -- don't, and specify token in configuration as %s. "
                "If token already exists and you want to generate a new one "
                "anyways - specify a new one via 'datalad.github.token-note' "
                "configuration variable"
                % (token_note, CONFIG_HUB_TOKEN_FIELD)
            )
        raise
    token = auth.token
    where_to_store = ui.question(
        title="Where to store token %s?" % _token_str(token),
        text="Empty string would result in the token not being "
             "stored for future reuse, so you will have to adjust "
             "configuration manually",
        choices=["global", "local", ""]
    )
    if where_to_store:
        try:
            # Using .add so other (possibly still legit tokens) are not lost
            if cfg.get(CONFIG_HUB_TOKEN_FIELD, None):
                lgr.info("Found that there is some other known tokens already, "
                         "adding one more")
            cfg.add(CONFIG_HUB_TOKEN_FIELD, auth.token,
                    where=where_to_store)
            lgr.info("Stored %s=%s in %s config.",
                     CONFIG_HUB_TOKEN_FIELD, _token_str(token),
                     where_to_store)
        except Exception as exc:
            lgr.error("Failed to store token: %s",
                      # sanitize away the token
                      exc_str(exc).replace(token, _token_str(token)))
            # assuming that it is ok to display the token to the user, since
            # otherwise it would be just lost.  ui  shouldn't log it (at least
            # ATM)
            ui.error(
                "Failed to store the token (%s), please store manually as %s"
                % (token, CONFIG_HUB_TOKEN_FIELD)
            )
    return token


def _gen_github_entity(
    github_login, github_passwd,
    github_organization
):
    for ses, cred in _gen_github_ses(github_login, github_passwd):
        if github_organization:
            try:
                yield ses.get_organization(github_organization), cred
            except gh.UnknownObjectException as e:
                # yoh thinks it might be due to insufficient credentials?
                raise ValueError('unknown organization "{}" [{}]'.format(
                                 github_organization,
                                 exc_str(e)))
        else:
            yield ses.get_user(), cred


def _make_github_repos(
        github_login, github_passwd, github_organization, rinfo, existing,
        access_protocol, dryrun):
    res = []
    if not rinfo:
        return res  # no need to even try!

    ncredattempts = 0
    # determine the entity under which to create the repos.  It might be that
    # we would need to check a few credentials
    for entity, cred in _gen_github_entity(
            github_login,
            github_passwd,
            github_organization):
        lgr.debug("Using entity %s with credential %s", entity, cred)
        ncredattempts += 1
        for ds, reponame in rinfo:
            lgr.debug("Trying to create %s for %s", reponame, ds)
            try:
                res_ = _make_github_repo(
                    github_login,
                    entity,
                    reponame,
                    existing,
                    access_protocol,
                    dryrun)
                # output will contain whatever is returned by _make_github_repo
                # but with a dataset prepended to the record
                res.append((ds,) + assure_tuple_or_list(res_))
            except gh.BadCredentialsException as e:
                if res:
                    # so we have succeeded with at least one repo already -
                    # we should not try any other credential.
                    # TODO: may be it would make sense to have/use different
                    # credentials for different datasets e.g. if somehow spread
                    # across different organizations? but it is not the case here
                    # IMHO (-- yoh)
                    raise e
                # things blew up, wipe out cred store, if anything is in it
                if cred:
                    lgr.warning("Authentication failed using %s.", cred.name)
                else:
                    lgr.warning("Authentication failed using a token.")
                break  # go to the next attempt to authenticate
        if res:
            return res

    # External loop should stop querying for the next possible way when it succeeds,
    # so we should never get here if everything worked out
    if ncredattempts:
        raise AccessDeniedError(
            "Tried %d times to get authenticated access to GitHub but kept failing"
            % ncredattempts
        )
    else:
        raise RuntimeError("Did not even try to create a repo on github")


def _make_github_repo(github_login, entity, reponame, existing, access_protocol, dryrun):
    repo = None
    try:
        repo = entity.get_repo(reponame)
    except gh.GithubException as e:
        if e.status != 404:
            # this is not a not found message, raise
            raise e
        lgr.debug(
            'To be created repository "%s" does not yet exist on Github',
            reponame)

    if repo is not None:
        if existing in ('skip', 'reconfigure'):
            access_url = get_repo_url(repo, access_protocol, github_login)
            return access_url, existing == 'skip'
        elif existing == 'error':
            msg = 'repository "{}" already exists on Github'.format(reponame)
            if dryrun:
                lgr.error(msg)
            else:
                raise ValueError(msg)
        else:
            RuntimeError('to must not happen')

    if repo is None and not dryrun:
        try:
            repo = entity.create_repo(
                reponame,
                # TODO description='',
                # TODO homepage='',
                # TODO private=False,
                has_issues=False,
                has_wiki=False,
                has_downloads=False,
                auto_init=False)
        except gh.GithubException as e:
            msg = "Github {}: {}".format(
                e.data.get('message', str(e) or 'unknown'),
                ', '.join([err.get('message')
                           for err in e.data.get('errors', [])
                           if 'message' in err]))
            raise RuntimeError(msg)

    if repo is None and not dryrun:
        raise RuntimeError(
            'something went wrong, we got no Github repository')

    if dryrun:
        return '{}:github/.../{}'.format(access_protocol, reponame), False
    else:
        # report URL for given access protocol
        return get_repo_url(repo, access_protocol, github_login), False