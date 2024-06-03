# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
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
import warnings
from urllib.parse import urljoin

import requests

from datalad.distributed.create_sibling_ghlike import (
    _create_sibling,
    _GitHubLike,
)
from datalad.distribution.dataset import datasetmethod
from datalad.interface.base import (
    Interface,
    build_doc,
    eval_results,
)
from datalad.support.constraints import (
    EnsureChoice,
    EnsureNone,
    EnsureStr,
)
from datalad.support.param import Parameter

lgr = logging.getLogger('datalad.distribution.create_sibling_github')


class _GitHub(_GitHubLike):
    """Customizations for the GitHub platform"""
    name = 'github'
    fullname = 'GitHub'
    response_code_unauthorized = 401
    create_org_repo_endpoint = 'orgs/{organization}/repos'
    create_user_repo_endpoint = 'user/repos'
    get_authenticated_user_endpoint = 'user'
    get_repo_info_endpoint = 'repos/{user}/{repo}'
    extra_remote_settings = {
        # first make sure that annex doesn't touch this one
        # but respect any existing config
        'annex-ignore': 'true',
        # first push should separately push active branch first
        # to overcome github issue of choosing "default" branch
        # alphabetically if its name does not match the default
        # branch for the user (or organization) which now defaults
        # to "main"
        'datalad-push-default-first': 'true'
    }

    def repo_create_response(self, r):
        """
        At present the only difference from the GHlike implementation
        is the detection of an already existing repo in a 422 response.
        """
        try:
            response = r.json()
        except Exception as e:
            lgr.debug('Cannot get JSON payload of %s [%s]' , r, e)
            response = {}
        lgr.debug('%s responded with %s %s', self.fullname, r, response)
        if r.status_code == requests.codes.created:
            return dict(
                status='ok',
                preexisted=False,
                # perform some normalization
                reponame=response.get('name'),
                private=response.get('private'),
                clone_url=response.get('clone_url'),
                ssh_url=response.get('ssh_url'),
                html_url=response.get('html_url'),
                # and also return in full
                host_response=response,
            )
        elif r.status_code == requests.codes.unprocessable and \
                any('already exist' in e.get('message', '')
                    for e in response.get('errors', [])):
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

    def repo_delete_request(self, orguser, reponame):
        r = requests.delete(
            urljoin(
                self.api_url,
                self.get_repo_info_endpoint.format(
                    user=orguser,
                    repo=reponame)),
            headers=self.request_headers,
        )
        # make sure any error-like situation causes noise
        r.raise_for_status()


@build_doc
class CreateSiblingGithub(Interface):
    """Create dataset sibling on GitHub.org (or an enterprise deployment).

    GitHub is a popular commercial solution for code hosting and collaborative
    development. GitHub cannot host dataset content (but see LFS,
    http://handbook.datalad.org/r.html?LFS). However, in combination with other
    data sources and siblings, publishing a dataset to GitHub can facilitate
    distribution and exchange, while still allowing any dataset consumer to
    obtain actual data content from alternative sources.

    In order to be able to use this command, a personal access token has to be
    generated on the platform (Account->Settings->Developer Settings->Personal
    access tokens->Generate new token).

    This command can be configured with
    "datalad.create-sibling-ghlike.extra-remote-settings.NETLOC.KEY=VALUE" in
    order to add any local KEY = VALUE configuration to the created sibling in
    the local `.git/config` file. NETLOC is the domain of the Github instance to
    apply the configuration for.
    This leads to a behavior that is equivalent to calling datalad's
    ``siblings('configure', ...)``||``siblings configure`` command with the
    respective KEY-VALUE pair after creating the sibling.
    The configuration, like any other, could be set at user- or system level, so
    users do not need to add this configuration to every sibling created with
    the service at NETLOC themselves.

    .. versionchanged:: 0.16
       || REFLOW >>
       The API has been aligned with the some
       ``create_sibling_...||create-sibling-...`` commands of other GitHub-like
       services, such as GOGS, GIN, GitTea.<< REFLOW ||

    .. deprecated:: 0.16
       The ``dryrun||--dryrun`` option will be removed in a future release, use
       the renamed ``dry_run||--dry-run`` option instead.
       The ``github_login||--github-login`` option will be removed in a future
       release, use the ``credential||--credential`` option instead.
       The ``github_organization||--github-organization`` option will be
       removed in a future release, prefix the repository name with ``<org>/``
       instead.
    """

    _examples_ = [
        dict(text="Use a new sibling on GIN as a common data source that is "
                  "auto-available when cloning from GitHub",
             code_py="""\
                 > ds = Dataset('.')

                 # the sibling on GIN will host data content
                 > ds.create_sibling_gin('myrepo', name='gin')

                 # the sibling on GitHub will be used for collaborative work
                 > ds.create_sibling_github('myrepo', name='github')

                 # register the storage of the public GIN repo as a data source
                 > ds.siblings('configure', name='gin', as_common_datasrc='gin-storage')

                 # announce its availability on github
                 > ds.push(to='github')
                 """,
             code_cmd="""\
                 % datalad create-sibling-gin myrepo -s gin

                 # the sibling on GitHub will be used for collaborative work
                 % datalad create-sibling-github myrepo -s github

                 # register the storage of the public GIN repo as a data source
                 % datalad siblings configure -s gin --as-common-datasrc gin-storage

                 # announce its availability on github
                 % datalad push --to github
                 """,
             ),
    ]

    _params_ = _GitHub.create_sibling_params
    _params_['api']._doc = """\
        URL of the GitHub instance API"""
    # special casing for deprecated mode
    _params_['existing'].constraints = EnsureChoice(
        'skip', 'error', 'reconfigure', 'replace')
    _params_['existing']._doc += """\
        DEPRECATED DANGER ZONE: With 'replace', an existing repository will be
        irreversibly removed, re-initialized, and the sibling
        (re-)configured (thus implies 'reconfigure').
        `replace` could lead to data loss! In interactive sessions a
        confirmation prompt is shown, an exception is raised in non-interactive
        sessions. The 'replace' mode will be removed in a future release."""
    # deprecated options
    _params_.update(
        github_login=Parameter(
            args=('--github-login',),
            constraints=EnsureStr() | EnsureNone(),
            metavar='TOKEN',
            doc="""Deprecated, use the credential parameter instead.
            If given must be a personal access token."""),
        github_organization=Parameter(
            args=('--github-organization',),
            constraints=EnsureStr() | EnsureNone(),
            metavar='NAME',
            doc="""Deprecated, prepend a repo name with an '<orgname>/'
            prefix instead."""),
        dryrun=Parameter(
            args=("--dryrun",),
            action="store_true",
            doc="""Deprecated. Use the renamed ``dry_run||--dry-run``
            parameter"""),
    )

    @staticmethod
    @datasetmethod(name='create_sibling_github')
    @eval_results
    def __call__(
            reponame,
            *,
            dataset=None,
            recursive=False,
            recursion_limit=None,
            name='github',
            existing='error',
            github_login=None,
            credential=None,
            github_organization=None,
            access_protocol='https',
            publish_depends=None,
            private=False,
            description=None,
            dryrun=False,
            dry_run=False,
            api='https://api.github.com'):
        if dryrun and not dry_run:
            # the old one is used, and not in agreement with the new one
            warnings.warn(
                "datalad-create-sibling-github's `dryrun` option is "
                "deprecated and will be removed in a future release, "
                "use the renamed `dry_run/--dry-run` option instead.",
                DeprecationWarning)
            dry_run = dryrun

        if api == 'https://api.github.com':
            token_info = \
                'Visit https://github.com/settings/tokens to create a token.'
        else:
            token_info = 'Log into the platform, and visit [Account->' \
                         'Settings->Developer Settings->' \
                         'Personal access tokens->Generate new token] ' \
                         'to create a new token.'
        if github_login:
            warnings.warn(
                "datalad-create-sibling-github's `github_login` option is "
                "deprecated and will be removed in a future release, "
                "use the `credential` option instead.",
                DeprecationWarning)
            from unittest.mock import patch

            # shoehorn the token into an env var to read it out using the
            # normal procedures internally
            with patch.dict(
                    'os.environ',
                    {'DATALAD_CREDENTIAL_GITHUBLOGINARG_TOKEN': github_login}):
                platform = _GitHub(
                    api, 'githubloginarg', require_token=not dry_run,
                    token_info=token_info)
        else:
            platform = _GitHub(api, credential, require_token=not dry_run,
                               token_info=token_info)

        if github_organization:
            warnings.warn(
                "datalad-create-sibling-github's `github_organization` "
                "option is deprecated and will be removed in a future "
                "release, prefix the repository name with `<org>/` instead.",
                DeprecationWarning)
            reponame = f'{github_organization}/{reponame}'

        yield from _create_sibling(
            platform=platform,
            reponame=reponame,
            dataset=dataset,
            recursive=recursive,
            recursion_limit=recursion_limit,
            name=name,
            existing=existing,
            access_protocol=access_protocol,
            publish_depends=publish_depends,
            private=private,
            description=description,
            dry_run=dry_run,
        )
