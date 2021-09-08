# API calls

# base url
#   https://try.gogs.io/api/v1/user/repos
#   https://api.github.com

# headers (uniform for both)
#   -H "Content-Type: application/json" \
#   -H "Authorization: token <token>" \

# create user repo
#   -d '{"name": "myrepo", "private": true, "description": "what a dummy?!"}' \
#   BASE/user/repos
# properties supported for GH: https://docs.github.com/en/rest/reference/repos#create-a-repository-for-the-authenticated-user
# overlap with GOGS properties is
# - name, description, private, auto_init
# - given auto_init should be False always, this should be enough

# create org repo
# - GH:   BASE/orgs/<org>/repos
# - GOGS: BASE/org/<org>/repos

# congruent parts of an API response to a repo creation
# Example response GitHub
# {
#   "name": "createpriv1",
#   "full_name": "datalad/createpriv1",
#   "private": true,
#   "owner": {
#     "login": "datalad",
#   },
#   "description": "what a dummy2?!",
#   "fork": false,
#   "created_at": "2021-08-30T07:42:05Z",
#   "updated_at": "2021-08-30T07:42:05Z",
#   "html_url": "https://github.com/datalad/createpriv1",
#   "ssh_url": "git@github.com:datalad/createpriv1.git",
#   "clone_url": "https://github.com/datalad/createpriv1.git",
#   "size": 0,
#   "default_branch": "master",
#   "permissions": {
#     "admin": true,
#     "push": true,
#     "pull": true
#   },
# }

#  Example response GOGS
# {
#   "name": "createpriv2",
#   "full_name": "dataladtesterorg/createpriv2",
#   "private": false,
#   "owner": {
#     "login": "dataladtesterorg",
#   },
#   "description": "",
#   "fork": false,
#   "created_at": "0001-01-01T00:00:00Z",
#   "updated_at": "0001-01-01T00:00:00Z",
#   "html_url": "https://try.gogs.io/dataladtesterorg/createpriv2",
#   "ssh_url": "git@try.gogs.io:dataladtesterorg/createpriv2.git",
#   "clone_url": "https://try.gogs.io/dataladtesterorg/createpriv2.git",
#   "size": 0,
#   "default_branch": "",
#   "permissions": {
#     "admin": true,
#     "push": true,
#     "pull": true
#   }
# }

import logging
import re
from urllib.parse import (
    urljoin,
    urlparse,
)
import requests

from datalad.downloaders.credentials import Token
from datalad.downloaders.http import DEFAULT_USER_AGENT
from datalad.support.param import Parameter
from datalad.support.constraints import (
    EnsureChoice,
    EnsureNone,
    EnsureStr,
)
from datalad.interface.results import get_status_dict
from datalad.interface.common_opts import (
    recursion_flag,
    recursion_limit,
    publish_depends,
)
from datalad.distribution.dataset import (
    EnsureDataset,
    require_dataset,
)

lgr = logging.getLogger('datalad.distributed.create_sibling_ghlike')


class _GitHubLike(object):
    name = None
    fullname = None
    create_org_repo_endpoint = None
    create_user_repo_endpoint = None
    get_authenticated_user_endpoint = None
    get_repo_info_endpoint = None
    response_code_repo_created = requests.codes.created
    response_code_unauthorized = requests.codes.forbidden

    extra_remote_settings = {}

    create_sibling_params = dict(
        dataset=Parameter(
            args=("--dataset", "-d",),
            doc="""dataset to create the publication target for. If not given,
            an attempt is made to identify the dataset based on the current
            working directory""",
            constraints=EnsureDataset() | EnsureNone()),
        reponame=Parameter(
            args=('reponame',),
            metavar='[<org-name>/]<repo-(base)name>',
            doc="""repository name, optionally including an '<organization>/'
            prefix if the repository shall not reside under a user's namespace.
            When operating recursively, a suffix will be appended to this name
            for each subdataset""",
            constraints=EnsureStr()),
        recursive=recursion_flag,
        recursion_limit=recursion_limit,
        name=Parameter(
            args=('-s', '--name',),
            metavar='NAME',
            doc="""name of the sibling in the local dataset installation
            (remote name)""",
            constraints=EnsureStr() | EnsureNone()),
        existing=Parameter(
            args=("--existing",),
            constraints=EnsureChoice(
                'skip', 'error', 'reconfigure', 'replace'),
            doc="""behavior when already existing or configured
            siblings are discovered: skip the dataset ('skip'), update the
            configuration ('reconfigure'), or fail ('error').
            DANGER ZONE: With 'replace', an existing repository will be
            irreversibly removed, re-initialized, and the sibling
            (re-)configured (thus implies 'reconfigure').
            `replace` could lead to data loss! In interactive a confirmation
            prompt is shown, an exception is raised in non-interactive
            sessions.""",),
        credential=Parameter(
            args=('--credential',),
            constraints=EnsureStr() | EnsureNone(),
            metavar='NAME',
            doc="""name of the credential providing a personal access token
            to be used for authorization. The token can be supplied via
            configuration setting 'datalad.credential.<name>.token', or
            environment variable DATALAD_CREDENTIAL_<NAME>_TOKEN, or will
            be queried from the active credential store using the provided
            name."""),
        api=Parameter(
            args=('--api',),
            constraints=EnsureStr() | EnsureNone(),
            metavar='URL',
            # TODO consider default instance via config
            doc="""API endpoint of the Git hosting service instance"""),
        access_protocol=Parameter(
            args=("--access-protocol",),
            # TODO possibly extend with 'https/ssh' for hybrid push/pull
            # access https://github.com/datalad/datalad/issues/5939
            constraints=EnsureChoice('https', 'ssh'),
            doc="""access protocol/URL to configure for the sibling"""),
        publish_depends=publish_depends,
        private=Parameter(
            args=("--private",),
            action="store_true",
            default=False,
            doc="""if set, create a private repository"""),
        dry_run=Parameter(
            args=("--dry-run",),
            action="store_true",
            doc="""if set, no repository will be created, only tests for
            name collisions will be performed, and would-be repository names
            are reported for all relevant datasets"""),
    )

    def __init__(self, url, credential, require_token=True):
        if not url:
            raise ValueError(f'API URL required for {self.fullname}')

        self.api_url = url
        self._user_info = None

        try:
            # TODO platform-specific doc URL for token generation
            self.auth = Token(credential, url=url)()['token']
        except Exception as e:
            lgr.debug('Token retrieval failed: %s', e)
            lgr.warning(
                'Cannot determine authorization token for %s', credential)
            if require_token:
                raise ValueError(
                    f'Authorization required for {self.fullname}, '
                    f'cannot find token for a credential {credential}.')
            else:
                lgr.warning("No token found for credential '%s'", credential)
                self.auth = 'NO-TOKEN-AVAILABLE'

        self.request_headers = {
            'user-agent': DEFAULT_USER_AGENT,
            'authorization': f'token {self.auth}',
        }

    @property
    def authenticated_user(self):
        if self._user_info:
            return self._user_info

        endpoint = urljoin(self.api_url, self.get_authenticated_user_endpoint)
        headers = self.request_headers
        r = requests.get(endpoint, headers=headers)
        # make sure any error-like situation causes noise
        r.raise_for_status()
        self._user_info = r.json()
        return self._user_info

    # TODO what are the actual constraints?
    def normalize_reponame(self, path):
        """Turn name (e.g. path) into a Github compliant repository name
        """
        return re.sub(r'\s+', '_', re.sub(r'[/\\]+', '-', path))

    def get_dataset_reponame_mapping(
            self, ds, name, reponame, existing, recursive, recursion_limit,
            res_kwargs):
        """
        """
        dss = _get_present_datasets(ds, recursive, recursion_limit)
        # check for existing remote configuration
        toprocess = []
        toyield = []
        for d in dss:
            if name in d.repo.get_remotes():
                toyield.append(get_status_dict(
                    ds=d,
                    status='error' if existing == 'error' else 'notneeded',
                    message=('already has a configured sibling "%s"', name),
                    **res_kwargs)
                )
                continue
            gh_reponame = reponame if d == ds else \
                '{}-{}'.format(
                    reponame,
                    self.normalize_reponame(
                        str(d.pathobj.relative_to(ds.pathobj))))
            toprocess.append((d, gh_reponame))
        return toprocess, toyield

    def get_siblingname(self, siblingname):
        if siblingname:
            return siblingname

        if self.api_url:
            siblingname = urlparse(self.api_url).netloc

        if not siblingname:
            raise ValueError(
                'No valid sibling name given or determined: {}'.format(
                    siblingname))

        return siblingname

    def create_repo(self, ds, reponame, organization, private, dry_run,
                    existing):
        # status='ok' when all is good
        # status='error' when unrecoverably broken
        # status='impossible' when recoverably broken
        # raise for any handled condition
        res = self.repo_create_request(
            reponame, organization, private, dry_run)

        if existing == 'reconfigure' \
                and res.get('status') == 'impossible' and \
                res.get('preexisted'):
            # query information on the existing repo and use that
            # to complete the task
            orguser = organization or self.authenticated_user['login']
            r = requests.get(
                urljoin(
                    self.api_url,
                    self.get_repo_info_endpoint.format(
                        user=orguser,
                        repo=reponame)),
                headers=self.request_headers,
            )
            # make sure any error-like situation causes noise
            r.raise_for_status()
            response = r.json()
            res.update(
                status='notneeded',
                # return in full
                host_response=response,
                # perform some normalization
                **self.normalize_repo_properties(response)
            )

        # TODO intermediate error handling?

        return res

    def create_repos(self, dsrepo_map, siblingname, organization,
                     private, dry_run, res_kwargs,
                     existing, access_protocol,
                     publish_depends):
        """
        """

        for d, reponame in dsrepo_map:
            res = self.create_repo(
                d, reponame, organization, private, dry_run,
                existing)
            # blend reported results with standard properties
            res = dict(
                res,
                **res_kwargs)

            if res.get('preexisted') and existing == 'skip':
                # we came here, despite initial checking for conflicting
                # sibling names. this means we found an unrelated repo
                res['status'] = 'error'
                res['message'] = (
                    "A repository '%s' already exists at '%s', "
                    "use existing=reconfigure to use it as a sibling",
                    reponame, self.api_url)

            if 'message' not in res:
                res['message'] = (
                    "sibling repository '%s' created at %s",
                    siblingname, res.get('html_url')
                )
            # report to caller
            yield get_status_dict(**res)

            if res['status'] not in ('ok', 'notneeded'):
                # something went wrong, do not proceed
                continue

            if dry_run:
                continue

            if res['status'] == 'notneeded' \
                    and existing not in ('reconfigure', 'replace'):
                # nothing to do anymore, when no reconfiguration is desired
                continue

            # lastly configure the local datasets
            for var_name, var_value in \
                    self.extra_remote_settings.items():
                var = 'remote.{}.{}'.format(siblingname, var_name)
                if var not in d.config:
                    d.config.add(var, var_value, where='local')
            yield from d.siblings(
                'configure',
                name=siblingname,
                url=res['ssh_url']
                if access_protocol == 'ssh'
                else res['clone_url'],
                recursive=False,
                # TODO fetch=True, maybe only if one existed already
                publish_depends=publish_depends,
                result_renderer='disabled')

    def repo_create_request(self, reponame, organization, private,
                            dry_run=False):
        """
        """
        endpoint = urljoin(
            self.api_url,
            self.create_org_repo_endpoint.format(
                organization=organization)
            if organization else
            self.create_user_repo_endpoint)
        data = {
            'name': reponame,
            'description': 'some default',
            'private': private,
            'auto_init': False,
        }
        headers = self.request_headers

        if dry_run:
            return dict(
                status='ok',
                request_url=endpoint,
                request_data=data,
                request_headers=headers,
            )
        r = requests.post(
            endpoint,
            json=data,
            headers=headers,
        )
        return self.repo_create_response(r)

    def repo_create_response(self, r):
        """
        """
        try:
            response = r.json()
        except Exception as e:
            lgr.debug('Cannot get JSON payload of %s [%s]' , r, e)
            response = {}
        lgr.debug('%s responded with %s %s', self.fullname, r, response)
        if r.status_code == self.response_code_repo_created:
            return dict(
                status='ok',
                preexisted=False,
                # return in full
                host_response=response,
                # perform some normalization
                **self.normalize_repo_properties(response)
            )
        elif r.status_code == requests.codes.unprocessable and \
                'already exist' in response.get('message', ''):
            return dict(
                status='impossible',
                message='repository already exists',
                preexisted=True,
            )
        elif r.status_code == self.response_code_unauthorized:
            return dict(
                status='error',
                message=('unauthorized: %s', response.get('message')),
            )
        # make sure any error-like situation causes noise
        r.raise_for_status()
        # catch-all
        raise RuntimeError(f'Unexpected host response: {response}')

    def normalize_repo_properties(self, response):
        """Normalize the essential response properties for the result record
        """
        return dict(
            reponame=response.get('name'),
            private=response.get('private'),
            clone_url=response.get('clone_url'),
            ssh_url=response.get('ssh_url'),
            html_url=response.get('html_url'),
        )


def _create_sibling(
        platform,
        reponame,
        dataset=None,
        recursive=False,
        recursion_limit=None,
        name=None,
        existing='error',
        access_protocol='https',
        publish_depends=None,
        private=False,
        dry_run=False):
    """
    """

    orgname, reponame = split_org_repo(reponame)

    # apply whatever normalization or default selection
    name = platform.get_siblingname(name)

    lgr.debug("Repository organization name: '%s'", orgname)

    if reponame != platform.normalize_reponame(reponame):
        raise ValueError(
            f'Invalid name for a {platform.fullname} project: {reponame}')

    lgr.debug("Repository basename: '%s'", reponame)

    # what to operate on
    ds = require_dataset(
        dataset,
        check_installed=True,
        purpose=f'create {platform.fullname} sibling(s)')

    res_kwargs = dict(
        action=\
        f'create_sibling_{platform.name} [dry-run]'
        if dry_run else
        f'create_sibling_{platform.name}',
        logger=lgr,
        refds=ds.path,
    )

    toprocess, filterresults = platform.get_dataset_reponame_mapping(
        ds, name, reponame, existing, recursive, recursion_limit,
        res_kwargs
    )
    yield from filterresults

    if not toprocess:
        # all skipped
        return

    lgr.debug("Will process %i dataset(s)", len(toprocess))

    yield from platform.create_repos(
        toprocess,
        name,
        orgname,
        private,
        dry_run,
        res_kwargs,
        existing,
        access_protocol,
        publish_depends,
    )


def split_org_repo(name):
    """Split a potential organization name prefix from a repo's full name

    Returns
    -------
    (None, reponame) or (orgname, reponame)
    """
    split = name.split('/', maxsplit=1)
    if len(split) < 2:
        return None, name
    else:
        return split[0], split[1]


def _get_present_datasets(ds, recursive, recursion_limit):
    """
    """
    # gather datasets and essential info
    # dataset instance and mountpoint relative to the top
    toprocess = [ds]
    if recursive:
        for sub in ds.subdatasets(
                # we want to report on missing dataset in here
                fulfilled=None,
                recursive=recursive,
                recursion_limit=recursion_limit,
                result_xfm='datasets'):
            if not sub.is_installed():
                lgr.info('Ignoring unavailable subdataset %s', sub)
                continue
            toprocess.append(sub)
    return toprocess
