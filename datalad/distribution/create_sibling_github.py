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
from datalad import cfg

from datalad.interface.common_opts import recursion_flag, recursion_limit
from datalad.downloaders.credentials import UserPassword
from datalad.dochelpers import exc_str
from datalad.utils import assure_list
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureStr, EnsureNone
from datalad.support.constraints import EnsureChoice
from datalad.support.exceptions import MissingExternalDependency
from ..interface.base import Interface
from datalad.distribution.dataset import EnsureDataset, datasetmethod, \
    require_dataset, Dataset
from .add_sibling import AddSibling

lgr = logging.getLogger('datalad.distribution.create_sibling_github')


def _get_github_entity(gh, cred, github_user, github_passwd, github_organization):
    # figure out authentication
    if not (github_user and github_passwd):
        # access to the system secrets
        if github_user:
            # check that they keystore knows about this user
            if github_user != cred.get('user', github_user):
                # there is a mismatch, we need to ask
                creds = cred.enter_new()
                github_user = creds['user']
                github_passwd = creds['password']

        # if a user is provided, go with it, don't even ask any store
        if github_user is None and not cred.is_known:
            # let's figure out authentication
            if github_user is None:
                # check if there is an oauth token from
                # https://github.com/sociomantic/git-hub
                github_user = cfg.get('hub.oauthtoken', None)

        if github_user is None:
            # still nothing, ask if necessary
            creds = cred()
            github_user = creds['user']
            github_passwd = creds['password']

    # this will always succeed, but it might later throw an exception
    # if the credentials were wrong
    # XXX make sure to wipe out known credentials if that happens
    authed_gh = gh.Github(
        github_user,
        password=github_passwd)

    try:
        if github_organization:
            try:
                entity = authed_gh.get_organization(github_organization)
            except gh.UnknownObjectException as e:
                raise ValueError('unknown organization "{}" [{}]'.format(
                                 github_organization,
                                 exc_str(e)))
        else:
            entity = authed_gh.get_user()
    except gh.BadCredentialsException as e:
        # things blew up, wipe out cred store, if anything is in it
        if cred.is_known:
            cred.delete()
        raise e

    return entity


def _make_github_repos(
        gh, github_user, github_passwd, github_organization, rinfo, existing,
        access_protocol, dryrun):
    cred = UserPassword('github', 'https://github.com/login')

    # determine the entity under which to create the repos
    entity = _get_github_entity(
        gh,
        cred,
        github_user,
        github_passwd,
        github_organization)

    res = []
    for ds, reponame in rinfo:
        try:
            access_url, existed = _make_github_repo(
                gh,
                entity,
                reponame,
                existing,
                access_protocol,
                dryrun)
            res.append((ds, access_url, existed))
        except gh.BadCredentialsException as e:
            # things blew up, wipe out cred store, if anything is in it
            if cred.is_known:
                cred.delete()
            raise e
    return res


def _make_github_repo(gh, entity, reponame, existing, access_protocol, dryrun):
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
            access_url = getattr(repo, '{}_url'.format(access_protocol))
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
                e.data.get('message', 'unknown'),
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
        return getattr(repo, '{}_url'.format(access_protocol)), False


# presently only implemented method to turn subdataset paths into Github
# compliant repository name suffixes
template_fx = lambda x: re.sub(r'\s+', '_', re.sub(r'[/\\]+', '-', x))


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
    :kbd:`git hub setup`.
    """

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
        sibling_name=Parameter(
            args=('--sibling-name',),
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
        github_user=Parameter(
            args=('--github-user',),
            constraints=EnsureStr() | EnsureNone(),
            metavar='NAME',
            doc="""Github user name"""),
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
            constraints=EnsureChoice('git', 'ssh'),
            doc="""Which access protocol/URL to configure for the sibling"""),
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
            sibling_name='github',
            existing='error',
            github_user=None,
            github_passwd=None,
            github_organization=None,
            access_protocol='git',
            dryrun=False):
        try:
            # this is an absolute leaf package, import locally to avoid
            # unecessary dependencies
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
            for d in ds.get_subdatasets(
                    fulfilled=None,  # we want to report on missing dataset in here
                    absolute=False,
                    recursive=recursive,
                    recursion_limit=recursion_limit):
                sub = Dataset(opj(ds.path, d))
                if not sub.is_installed():
                    lgr.info('Ignoring unavailable subdataset %s', sub)
                    continue
                toprocess.append((sub, d))

        # check for existing remote configuration
        filtered = []
        for d, mp in toprocess:
            if sibling_name in d.repo.get_remotes():
                if existing == 'error':
                    msg = '{} already had a configured sibling "{}"'.format(
                        d, sibling_name)
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

        # actually make it happen on Github
        rinfo = _make_github_repos(
            gh, github_user, github_passwd, github_organization, filtered,
            existing, access_protocol, dryrun)

        # lastly configure the local datasets
        for d, url, existed in rinfo:
            if not dryrun:
                AddSibling()(
                    dataset=d,
                    name=sibling_name,
                    url=url,
                    recursive=False,
                    # TODO fetch=True, maybe only if one existed already
                    force=existing in {'reconfigure'})

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
                        args.sibling_name,
                        d))
