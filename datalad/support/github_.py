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
from ..consts import (
    CONFIG_HUB_TOKEN_FIELD,
    GITHUB_TOKENS_URL,
)
from ..dochelpers import exc_str
from ..downloaders.credentials import Token
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
    if len(token) < 10:
        # for some reason too short to reveal even a part of it
        return "???TOOSHORT"
    return token[:3] + '...'


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


def _gen_github_ses(github_login):
    """Generate viable Github sessions

    The idea is that we keep trying "new" ways to authenticate until we either
    exhaust or external loop stops asking for more

    Parameters
    ----------
    github_login:

    Yields
    -------
    Github, token_str
      token_str is a shortened token string, so we do not reveal secret in full

    """
    if github_login == 'disabledloginfortesting':
        raise gh.BadCredentialsException(403, 'no login specified')

    # see if we have tokens - might be many. Doesn't cost us much so get at once
    tokens = unique(
        assure_list(cfg.get(CONFIG_HUB_TOKEN_FIELD, None)),
        reverse=True
    )

    # Check the tokens.  If login is provided, only the token(s) for the
    # login are considered. We consider oauth tokens as stored/used by
    # https://github.com/sociomantic/git-hub

    if github_login and tokens:
        # Take only the tokens which are Ok and correspond to that login
        tokens = _get_tokens_for_login(github_login, tokens)

    for token in tokens:
        try:
            yield gh.Github(token), _token_str(token)
        except gh.BadCredentialsException as exc:
            lgr.debug("Failed to obtain Github session for token %s: %s",
                      _token_str(token), exc_str(exc))

    # We got here so time to get/store token from credential store
    cred = _get_github_cred(github_login)
    while True:
        token = cred()['token']
        try:
            # ??? there was a comment   # None for cred so does not get killed
            # while returning None as cred.  Effect was not fully investigated from changing to return _token_str
            yield gh.Github(token), _token_str(token)
        except gh.BadCredentialsException as exc:
            lgr.debug("Failed to obtain Github session for token %s: %s",
                      _token_str(token), exc_str(exc))
        # if we are getting here, it means we are asked for more and thus
        # aforementioned one didn't work out :-/
        if ui.is_interactive:
            if cred is not None:
                if ui.yesno(
                    title="GitHub credentials",
                    text="Do you want to try (re)entering GitHub personal access token?"
                ):
                    cred.enter_new()
                else:
                    break
        else:
            # Nothing we could do
            lgr.warning(
                "UI is not interactive - we cannot query for more credentials"
            )
            break


def _get_github_cred(github_login=None):
    """Helper to create a github token credential"""
    cred_identity = "%s@github" % github_login if github_login else "github"
    return Token(cred_identity, GITHUB_TOKENS_URL)


def _gen_github_entity(
    github_login,
    github_organization
):
    for ses, token_str in _gen_github_ses(github_login):
        if github_organization:
            try:
                org = ses.get_organization(github_organization)
                lgr.info(
                    "Successfully obtained information about organization %s "
                    "using token %s", github_organization, token_str
                )
                yield org, token_str
            except gh.UnknownObjectException as e:
                # yoh thinks it might be due to insufficient credentials?
                raise ValueError('unknown organization "{}" [{}]'.format(
                                 github_organization,
                                 exc_str(e)))
            except gh.BadCredentialsException as e:
                lgr.warning(
                    "Having authenticated using a token %s, we failed (%s) to access "
                    "information about organization %s. We will try next "
                    "token (if any left available)",
                    token_str, e, github_organization
                )
                continue
        else:
            yield ses.get_user(), token_str


def _make_github_repos(
        github_login, github_organization, rinfo, existing,
        access_protocol, dryrun):
    res = []
    if not rinfo:
        return res  # no need to even try!

    ncredattempts = 0
    # determine the entity under which to create the repos.  It might be that
    # we would need to check a few credentials
    for entity, token_str in _gen_github_entity(
            github_login,
            github_organization):
        lgr.debug("Using entity %s with token %s", entity, token_str)
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
            except (gh.BadCredentialsException, gh.GithubException) as e:
                hint = None
                if (isinstance(e, gh.BadCredentialsException) and e.status != 403):
                    # e.g. while deleting a repository, just a generic GithubException is
                    # raised but code is 403. At least it is about permissions
                    pass
                elif e.status == 404:
                    # github hides away if repository might already be existing
                    # if token does not have sufficient credentials
                    hint = "Likely the token lacks sufficient permissions to "\
                            "assess if repository already exists or not"
                else:
                    # Those above we process, the rest - re-raise
                    raise
                lgr.warning("Failed to create repository while using token %s: %s%s",
                            token_str,
                            exc_str(e),
                            (" Hint: %s" % hint) if hint else "")

                if res:
                    # so we have succeeded with at least one repo already -
                    # we should not try any other credential.
                    # TODO: may be it would make sense to have/use different
                    # credentials for different datasets e.g. if somehow spread
                    # across different organizations? but it is not the case here
                    # IMHO (-- yoh)
                    raise e
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
        elif existing == 'replace':
            _msg = 'repository "%s" already exists on GitHub.' % reponame
            if dryrun:
                lgr.info(_msg + " Deleting (dry)")
            else:
                # Since we are running in the loop trying different tokens,
                # this message might appear twice. TODO: avoid
                if ui.is_interactive:
                    remove = ui.yesno(
                        "Do you really want to remove it?",
                        title=_msg,
                        default=False
                    )
                else:
                    raise RuntimeError(
                        _msg +
                        " Remove it manually first on GitHub or rerun datalad in "
                        "interactive shell to confirm this action.")
                if not remove:
                    raise RuntimeError(_msg)
                repo.delete()
                repo = None
        else:
            RuntimeError('must not happen')

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
            if e.status == 404:
                # can happen if credentials are not good enough!
                raise
            msg = "Github {} ({})".format(
                e.data.get('message', str(e) or 'unknown'),
                e.data.get('documentation_url', 'no url')
            )
            if e.data.get('errors'):
                msg += ': {}'.format(
                    ', '.join(
                        [
                            err.get('message')
                            for err in e.data.get('errors', [])
                            if 'message' in err
                        ]))
            raise RuntimeError(msg)

    if repo is None and not dryrun:
        raise RuntimeError(
            'something went wrong, we got no Github repository')

    if dryrun:
        return '{}:github/.../{}'.format(access_protocol, reponame), False
    else:
        # report URL for given access protocol
        return get_repo_url(repo, access_protocol, github_login), False
