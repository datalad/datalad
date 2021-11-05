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
from ..downloaders.credentials import Token
from ..ui import ui
from ..utils import (
    ensure_list,
    unique,
)
from .exceptions import (
    AccessDeniedError,
    CapturedException,
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
                " login name. Skipping", _token_str(t), CapturedException(exc))
    lgr.debug(
        "Selected %d tokens out of %d for the login %s",
        len(selected_tokens), len(tokens), login
    )
    return selected_tokens


def _gh_exception(exc_cls, status, data):
    """Compatibility wrapper for instantiating a GithubException.
    """
    try:
        exc = exc_cls(status, data, None)
    except TypeError:
        # Before PyGithub 1.5, GithubException had only two required arguments.
        exc = exc_cls(status, data)
    return exc


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
        raise _gh_exception(gh.BadCredentialsException,
                            403, 'no login specified')

    # see if we have tokens - might be many. Doesn't cost us much so get at once
    tokens = unique(
        ensure_list(cfg.get(CONFIG_HUB_TOKEN_FIELD, None)),
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
                      _token_str(token), CapturedException(exc))

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
                      _token_str(token), CapturedException(exc))
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
                raise ValueError('unknown organization "{}"'.format(
                                 github_organization)) from e
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


def _make_github_repos_(
        github_login, github_organization, rinfo, existing,
        access_protocol, private, dryrun):
    """Create a series of GitHub projects

    Yields
    ------
    tuple (Dataset instance, URL, bool)
    """
    if not rinfo:
        return  # no need to even try!

    auth_success = False
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
                    private,
                    dryrun)
                # output will contain whatever is returned by _make_github_repo
                # but with a dataset prepended to the record
                res_['ds'] = ds
                yield res_
                # track (through the keyhole of the backdoor) if we had luck
                # with the github credential set
                # which worked, whenever we have a good result, or where able to
                # determined, if a project already exists
                auth_success = auth_success or \
                    res_['status'] in ('ok', 'notneeded') or \
                    res_['preexisted']
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
                            CapturedException(e),
                            (" Hint: %s" % hint) if hint else "")

                if auth_success:
                    # so we have succeeded with at least one repo already -
                    # we should not try any other credential.
                    # TODO: may be it would make sense to have/use different
                    # credentials for different datasets e.g. if somehow spread
                    # across different organizations? but it is not the case here
                    # IMHO (-- yoh)
                    raise e
                break  # go to the next attempt to authenticate

        if auth_success:
            return

    # External loop should stop querying for the next possible way when it succeeds,
    # so we should never get here if everything worked out
    if ncredattempts:
        raise AccessDeniedError(
            "Tried %d times to get authenticated access to GitHub but kept failing"
            % ncredattempts
        )
    else:
        raise RuntimeError("Did not even try to create a repo on github")


def _make_github_repo(github_login, entity, reponame, existing,
                      access_protocol, private, dryrun):
    """Create a GitHub project

    Returns
    -------
    dict
      Keys/values are 'status' (str), 'url' (str), 'preexisted' (bool),
      'message' (str).

    Raises
    ------
    BadCredentialsException,
    GithubException
    """
    repo = None
    access_url = None
    try:
        repo = entity.get_repo(reponame)
        access_url = get_repo_url(repo, access_protocol, github_login)
    except gh.GithubException as e:
        if e.status != 404:
            # this is not a not found message, raise
            raise e
        lgr.debug(
            'To be created repository "%s" does not yet exist on Github',
            reponame)

    if repo is not None:
        res = dict(
            url=access_url,
            preexisted=True,
        )
        if existing in ('skip', 'reconfigure'):
            return dict(
                res,
                status='notneeded',
                preexisted=existing == 'skip',
            )
        elif existing == 'error':
            return dict(
                res,
                status='error',
                message=('repository "%s" already exists on Github', reponame),
            )
        elif existing == 'replace':
            _msg = ('repository "%s" already exists on GitHub.', reponame)
            # Since we are running in the loop trying different tokens,
            # this message might appear twice. TODO: avoid
            if ui.is_interactive:
                remove = ui.yesno(
                    "Do you really want to remove it?",
                    title=_msg[0] % _msg[1],
                    default=False
                )
            else:
                return dict(
                    res,
                    status='impossible',
                    message=(
                        _msg[0] + " Remove it manually first on GitHub or "
                        "rerun datalad in an interactive shell to confirm "
                        "this action.",
                        _msg[1]),
                )
            if not remove:
                return dict(
                    res,
                    status='impossible',
                    message=_msg,
                )
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
                private=private,
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
            return dict(
                res,
                status='error',
                message=msg,
            )

    if repo is None and not dryrun:
        raise RuntimeError(
            'something went wrong, we got no Github repository')

    # get definitive URL:
    # - use previously determined one
    # - or query a newly created project
    # - or craft one in dryrun mode
    access_url = access_url or '{}github.com{}{}/{}.git'.format(
        'https://' if access_protocol == 'https' else 'git@',
        '/' if access_protocol == 'https' else ':',
        # this will be the org, in case the repo will go under an org
        entity.login,
        reponame,
    ) if dryrun else get_repo_url(repo, access_protocol, github_login)

    return dict(
        status='ok',
        url=access_url,
        preexisted=False,
    )
