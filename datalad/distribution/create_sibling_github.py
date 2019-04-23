# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""High-level interface for creating a publication target on GitHub
"""

__docformat__ = 'restructuredtext'


import logging
import re

from os.path import join as opj
from os.path import relpath
from datalad import cfg

from ..ui import ui

from datalad.interface.common_opts import recursion_flag, recursion_limit
from datalad.interface.common_opts import publish_depends
from datalad.downloaders.credentials import UserPassword
from datalad.dochelpers import exc_str
from datalad.utils import (
    assure_list,
    assure_tuple_or_list,
    unique,
)
from datalad.support.param import Parameter
from datalad.support.network import URL
from datalad.support.constraints import EnsureStr, EnsureNone
from datalad.support.constraints import EnsureChoice
from datalad.support.exceptions import (
    MissingExternalDependency,
    AccessDeniedError,
)
from ..interface.base import Interface
from datalad.interface.base import build_doc
from datalad.distribution.dataset import EnsureDataset, datasetmethod, \
    require_dataset, Dataset
from datalad.distribution.siblings import Siblings

lgr = logging.getLogger('datalad.distribution.create_sibling_github')

CONFIG_HUB_TOKEN_FIELD = 'hub.oauthtoken'


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
    import github as gh
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
    import github as gh
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
            if not cred.is_known:
                cred.enter_new()
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
    import github as gh
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
    import github as gh
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
    import github as gh
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
    import github as gh
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


# presently only implemented method to turn subdataset paths into Github
# compliant repository name suffixes
template_fx = lambda x: re.sub(r'\s+', '_', re.sub(r'[/\\]+', '-', x))


@build_doc
class CreateSiblingGithub(Interface):
    """Create dataset sibling on Github.

    A repository can be created under a user's Github account, or any
    organization a user is a member of (given appropriate permissions).

    Recursive sibling creation for subdatasets is supported. A dataset
    hierarchy is represented as a flat list of Github repositories.

    Github cannot host dataset content. However, in combination with
    other data sources (and siblings), publishing a dataset to Github can
    facilitate distribution and exchange, while still allowing any dataset
    consumer to obtain actual data content from alternative sources.

    For Github authentication user credentials can be given as arguments.
    Alternatively, they are obtained interactively or queried from the systems
    credential store. Lastly, an *oauth* token stored in the Git
    configuration under variable *hub.oauthtoken* will be used automatically.
    Such a token can be obtained, for example, using the commandline Github
    interface (https://github.com/sociomantic/git-hub) by running:
    :kbd:`git hub setup` (if no 2FA is used).
    """
    # XXX prevent common args from being added to the docstring
    _no_eval_results = True

    _params_ = dict(
        dataset=Parameter(
            args=("--dataset", "-d",),
            doc="""specify the dataset to create the publication target for. If
                no dataset is given, an attempt is made to identify the dataset
                based on the current working directory""",
            constraints=EnsureDataset() | EnsureNone()),
        reponame=Parameter(
            args=('reponame',),
            metavar='REPONAME',
            doc="""Github repository name. When operating recursively,
            a suffix will be appended to this name for each subdataset""",
            constraints=EnsureStr()),
        recursive=recursion_flag,
        recursion_limit=recursion_limit,
        name=Parameter(
            args=('-s', '--name',),
            metavar='NAME',
            doc="""name to represent the Github repository in the local
            dataset installation""",
            constraints=EnsureStr()),
        existing=Parameter(
            args=("--existing",),
            constraints=EnsureChoice('skip', 'error', 'reconfigure'),
            metavar='MODE',
            doc="""desired behavior when already existing or configured
            siblings are discovered. 'skip': ignore; 'error': fail immediately;
            'reconfigure': use the existing repository and reconfigure the
            local dataset to use it as a sibling""",),
        github_login=Parameter(
            args=('--github-login',),
            constraints=EnsureStr() | EnsureNone(),
            metavar='NAME',
            doc="""Github user name or access token"""),
        github_passwd=Parameter(
            args=('--github-passwd',),
            constraints=EnsureStr() | EnsureNone(),
            metavar='PASSWORD',
            doc="""Github user password"""),
        github_organization=Parameter(
            args=('--github-organization',),
            constraints=EnsureStr() | EnsureNone(),
            metavar='NAME',
            doc="""If provided, the repository will be created under this
            Github organization. The respective Github user needs appropriate
            permissions."""),
        access_protocol=Parameter(
            args=("--access-protocol",),
            constraints=EnsureChoice('https', 'ssh'),
            doc="""Which access protocol/URL to configure for the sibling"""),
        publish_depends=publish_depends,
        dryrun=Parameter(
            args=("--dryrun",),
            action="store_true",
            doc="""If this flag is set, no communication with Github is
            performed, and no repositories will be created. Instead
            would-be repository names are reported for all relevant datasets
            """),
    )

    @staticmethod
    @datasetmethod(name='create_sibling_github')
    def __call__(
            reponame,
            dataset=None,
            recursive=False,
            recursion_limit=None,
            name='github',
            existing='error',
            github_login=None,
            github_passwd=None,
            github_organization=None,
            access_protocol='https',
            publish_depends=None,
            dryrun=False):
        try:
            # this is an absolute leaf package, import locally to avoid
            # unnecessary dependencies
            import github as gh
        except ImportError:
            raise MissingExternalDependency(
                'PyGitHub',
                msg='GitHub-related functionality is unavailable without this package')

        # what to operate on
        ds = require_dataset(
            dataset, check_installed=True, purpose='create Github sibling')
        # gather datasets and essential info
        # dataset instance and mountpoint relative to the top
        toprocess = [(ds, '')]
        if recursive:
            for sub in ds.subdatasets(
                    fulfilled=None,  # we want to report on missing dataset in here
                    recursive=recursive,
                    recursion_limit=recursion_limit,
                    result_xfm='datasets'):
                if not sub.is_installed():
                    lgr.info('Ignoring unavailable subdataset %s', sub)
                    continue
                toprocess.append((sub, relpath(sub.path, start=ds.path)))

        # check for existing remote configuration
        filtered = []
        for d, mp in toprocess:
            if name in d.repo.get_remotes():
                if existing == 'error':
                    msg = '{} already has a configured sibling "{}"'.format(
                        d, name)
                    if dryrun:
                        lgr.error(msg)
                    else:
                        raise ValueError(msg)
                elif existing == 'skip':
                    continue
            gh_reponame = '{}{}{}'.format(
                reponame,
                '-' if mp else '',
                template_fx(mp))
            filtered.append((d, gh_reponame))

        if not filtered:
            # all skipped
            return []

        # actually make it happen on Github
        rinfo = _make_github_repos(
            github_login, github_passwd, github_organization, filtered,
            existing, access_protocol, dryrun)

        # lastly configure the local datasets
        for d, url, existed in rinfo:
            if not dryrun:
                # first make sure that annex doesn't touch this one
                # but respect any existing config
                ignore_var = 'remote.{}.annex-ignore'.format(name)
                if not ignore_var in d.config:
                    d.config.add(ignore_var, 'true', where='local')
                Siblings()(
                    'configure',
                    dataset=d,
                    name=name,
                    url=url,
                    recursive=False,
                    # TODO fetch=True, maybe only if one existed already
                    publish_depends=publish_depends)

        # TODO let submodule URLs point to Github (optional)
        return rinfo

    @staticmethod
    def result_renderer_cmdline(res, args):
        from datalad.ui import ui
        res = assure_list(res)
        if args.dryrun:
            ui.message('DRYRUN -- Anticipated results:')
        if not len(res):
            ui.message("Nothing done")
        else:
            for d, url, existed in res:
                ui.message(
                    "'{}'{} configured as sibling '{}' for {}".format(
                        url,
                        " (existing repository)" if existed else '',
                        args.name,
                        d))
