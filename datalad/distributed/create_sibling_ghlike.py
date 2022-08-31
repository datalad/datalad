# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Tooling for creating a publication target on GitHub-like systems
"""

import logging
import re
from urllib.parse import (
    urljoin,
    urlparse,
)

import requests

from datalad.distribution.dataset import (
    EnsureDataset,
    require_dataset,
)
from datalad.downloaders.credentials import Token
from datalad.downloaders.http import DEFAULT_USER_AGENT
from datalad.interface.common_opts import (
    publish_depends,
    recursion_flag,
    recursion_limit,
)
from datalad.interface.results import get_status_dict
from datalad.support.constraints import (
    EnsureChoice,
    EnsureNone,
    EnsureStr,
)
from datalad.support.param import Parameter
from datalad.ui import ui
from datalad.utils import todo_interface_for_extensions


lgr = logging.getLogger('datalad.distributed.create_sibling_ghlike')


class _GitHubLike(object):
    """Helper class with a platform abstraction for GitHub-like services
    """
    # (short) lower-case name of the target platform
    name = None
    # (longer) name with fancy capitalization
    fullname = None
    # all API endpoint without base URL!
    # to create a repo in an organization
    create_org_repo_endpoint = None
    # to create a repo under the authenticated user
    create_user_repo_endpoint = None
    # query for props of the authenticated users
    get_authenticated_user_endpoint = None
    # query for repository properties
    get_repo_info_endpoint = None
    # HTTP response codes for particular events
    # repo created successfully
    response_code_repo_created = requests.codes.created
    # auth failure
    response_code_unauthorized = requests.codes.forbidden

    # extra config settings to be used for a remote pointing to the
    # target platform
    extra_remote_settings = {}

    # to be used (in modified form) by create_sibling_*() commands that
    # utilize this platform abstraction
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
                'skip', 'error', 'reconfigure'),
            doc="""behavior when already existing or configured
            siblings are discovered: skip the dataset ('skip'), update the
            configuration ('reconfigure'), or fail ('error').""",),
        credential=Parameter(
            args=('--credential',),
            constraints=EnsureStr() | EnsureNone(),
            metavar='NAME',
            doc="""name of the credential providing a personal access token
            to be used for authorization. The token can be supplied via
            configuration setting 'datalad.credential.<name>.token', or
            environment variable DATALAD_CREDENTIAL_<NAME>_TOKEN, or will
            be queried from the active credential store using the provided
            name. If none is provided, the host-part of the API URL is used
            as a name (e.g. 'https://api.github.com' -> 'api.github.com')"""),
        api=Parameter(
            args=('--api',),
            constraints=EnsureStr() | EnsureNone(),
            metavar='URL',
            # TODO consider default instance via config
            doc="""API endpoint of the Git hosting service instance"""),
        access_protocol=Parameter(
            args=("--access-protocol",),
            constraints=EnsureChoice('https', 'ssh', 'https-ssh'),
            doc="""access protocol/URL to configure for the sibling. With
            'https-ssh' SSH will be used for write access, whereas HTTPS
            is used for read access."""),
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

    def __init__(self, url, credential, require_token=True, token_info=None):
        if self.name is None or self.fullname is None:
            raise NotImplementedError(
                'GitHub-like platform must have name and fullname properties')
        if not url:
            raise ValueError(f'API URL required for {self.fullname}')

        self.api_url = url
        self._user_info = None
        self._set_request_headers(
            credential,
            f'An access token is required for {url}' \
            + f'. {token_info}' if token_info else '',
            require_token,
        )

    @todo_interface_for_extensions
    def _set_request_headers(self, credential_name, auth_info, require_token):
        if credential_name is None:
            credential_name = urlparse(self.api_url).netloc

        try:
            self.auth = Token(credential_name)(
                instructions=auth_info)['token']
        except Exception as e:
            lgr.debug('Token retrieval failed: %s', e)
            lgr.warning(
                'Cannot determine authorization token for %s', credential_name)
            if require_token:
                raise ValueError(
                    f'Authorization required for {self.fullname}, '
                    f'cannot find token for a credential {credential_name}.')
            else:
                lgr.warning("No token found for credential '%s'", credential_name)
                self.auth = 'NO-TOKEN-AVAILABLE'

        self.request_headers = {
            'user-agent': DEFAULT_USER_AGENT,
            'authorization': f'token {self.auth}',
        }

    @property
    def authenticated_user(self):
        """Lazy query/reporting of properties for the authenticated user

        Returns
        -------
        dict
        """
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
        """Turn name into a GitHub-like service compliant repository name

        Useful for sanitizing directory names.
        """
        return re.sub(r'\s+', '_', re.sub(r'[/\\]+', '-', path))

    def get_dataset_reponame_mapping(
            self, ds, name, reponame, existing, recursive, recursion_limit,
            res_kwargs):
        """Discover all relevant datasets locally, and build remote repo names
        """
        dss = _get_present_datasets(ds, recursive, recursion_limit)
        # check for existing remote configuration
        toprocess = []
        toyield = []
        for d in dss:
            if existing not in ('reconfigure', 'replace') and \
                    name in d.repo.get_remotes():
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
        """Generate a (default) sibling name, if none is given

        Returns
        -------
        str
        """
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
        """Create a repository on the target platform

        Returns
        -------
        dict
          Result record, with status='ok' when all is good, status='error'
          when unrecoverably broken, status='impossible' when recoverably
          broken

        Raises
        ------
        Exception
          Any unhandled condition (in particular unexpected non-success
          HTTP response codes) will raise an exception.
        """
        res = self.repo_create_request(
            reponame, organization, private, dry_run)

        if res.get('status') == 'impossible' and res.get('preexisted'):
            # we cannot create, because there is something in the target
            # spot
            orguser = organization or self.authenticated_user['login']

            if existing == 'reconfigure':
                # we want to use the existing one instead
                # query properties, report, and be done
                repo_props = self.repo_get_request(orguser, reponame)
                res.update(
                    status='notneeded',
                    # return in full
                    host_response=repo_props,
                    # perform some normalization
                    **self.normalize_repo_properties(repo_props)
                )
            elif existing == 'replace':
                # only implemented for backward compat with
                # create-sibling-github
                _msg = ('repository "%s" already exists', reponame)
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
                            _msg[0] + " Remove it manually first or "
                            "rerun DataLad in an interactive shell "
                            "to confirm this action.",
                            _msg[1]),
                    )
                if not remove:
                    return dict(
                        res,
                        status='impossible',
                        message=_msg,
                    )
                # remove the beast in cold blood
                self.repo_delete_request(
                    organization or self.authenticated_user['login'],
                    reponame)
                # try creating now
                return self.create_repo(
                    ds, reponame, organization, private, dry_run,
                    existing)

        # TODO intermediate error handling?

        return res

    def repo_get_request(self, orguser, reponame):
        """Perform request to query for repo properties

        Returns
        -------
        dict
          The JSON payload of the response.
        """
        # query information on the existing repo and use that
        # to complete the task
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
        return r.json()

    def repo_delete_request(self, orguser, reponame):
        """Perform request to delete a named repo on the platform

        Must be implemented in subclasses for particular target platforms.
        """
        raise NotImplementedError

    def create_repos(self, dsrepo_map, siblingname, organization,
                     private, dry_run, res_kwargs,
                     existing, access_protocol,
                     publish_depends):
        """Create a series of repos on the target platform

        This method handles common conditions in a uniform platform-agnostic
        fashion, and sets local sibling configurations for created/located
        repositories.

        Yields
        ------
        dict
          Result record
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
                if existing in ('reconfigure', 'replace'):
                    d.config.set(var, var_value, scope='local')
                elif var not in d.config:
                    d.config.add(var, var_value, scope='local')
            yield from d.siblings(
                'configure',
                name=siblingname,
                url=res['ssh_url']
                if access_protocol == 'ssh'
                else res['clone_url'],
                pushurl=res['ssh_url']
                if access_protocol == 'https-ssh' else None,
                recursive=False,
                # TODO fetch=True, maybe only if one existed already
                publish_depends=publish_depends,
                return_type='generator',
                result_renderer='disabled')

    def repo_create_request(self, reponame, organization, private,
                            dry_run=False):
        """Perform a request to create a repo on the target platform

        Also implements reporting of "fake" results in dry-run mode.

        Returns
        -------
        dict
          Result record, but see repo_create_response() for details.
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
        """Handling of repo creation request responses

        Normalizes error handling and reporting.

        Returns
        -------
        dict
          Result record

        Raises
        ------
        Exception
          Raises for any unhandled HTTP error response code.
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
        elif r.status_code in (self.response_code_unauthorized,
                               requests.codes.forbidden):
            return dict(
                status='error',
                message=('unauthorized: %s', response.get('message')),
            )
        elif r.status_code == requests.codes.internal_server_error:
            return dict(
                status='error',
                message=response.get('message', '').strip() or 'Server returned error code %d without any further information' % requests.codes.internal_server_error,
            )
        # make sure any error-like situation causes noise
        r.raise_for_status()
        # catch-all
        raise RuntimeError(f'Unexpected host response: {response}')

    def normalize_repo_properties(self, response):
        """Normalize the essential response properties for the result record

        Importantly, `clone_url` is a URL that DataLad can directly clone
        from, and that should be the default preferred access method for read
        access by the largest possible audience. Critically, a particular
        platform, might advertise SSH as default, but DataLad might promote
        anonymous HTTP-access as a default, if supported.

        Returns
        -------
        dict
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
    """Helper function to conduct sibling creation on a target platform

    Parameters match the respective create_sibling_*() commands.
    `platform` is an instance of a subclass of `_GitHubLike`.

    Yields
    ------
    dict
      Result record.
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
    """Return list of (sub)dataset instances for all locally present datasets
    """
    # gather datasets and essential info
    # dataset instance and mountpoint relative to the top
    toprocess = [ds]
    if recursive:
        for sub in ds.subdatasets(
                # we want to report on missing dataset in here
                state='any',
                recursive=recursive,
                recursion_limit=recursion_limit,
                result_xfm='datasets',
                result_renderer='disabled',
                return_type='generator'):
            if not sub.is_installed():
                lgr.info('Ignoring unavailable subdataset %s', sub)
                continue
            toprocess.append(sub)
    return toprocess
