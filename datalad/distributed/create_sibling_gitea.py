# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""High-level interface for creating a publication target on a Gitea instance
"""

import logging

import requests

from datalad.distributed.create_sibling_ghlike import _create_sibling
from datalad.distributed.create_sibling_gogs import _GOGS
from datalad.distribution.dataset import datasetmethod
from datalad.interface.base import (
    Interface,
    build_doc,
)
from datalad.interface.utils import eval_results

lgr = logging.getLogger('datalad.distributed.create_sibling_gitea')


class _Gitea(_GOGS):
    """Customizations for the Gitea platform"""
    name = 'gitea'
    fullname = 'Gitea'
    response_code_unauthorized = 401
    extra_remote_settings = {
        # first make sure that annex doesn't touch this one
        # but respect any existing config
        'annex-ignore': 'true',
    }

    def repo_create_response(self, r):
        """
        At present the only difference from the GHlike implementation
        is the detection of an already existing via a proper 409 response.
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
        elif r.status_code == requests.codes.conflict and \
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
        # make sure any error-like situation causes noise
        r.raise_for_status()
        # catch-all
        raise RuntimeError(f'Unexpected host response: {response}')


@build_doc
class CreateSiblingGitea(Interface):
    """Create a dataset sibling on a Gitea site

    Gitea is a lightweight, free and open source code hosting solution with
    low resource demands that enable running it on inexpensive devices like
    a Raspberry Pi.

    This command uses the main Gitea instance at https://gitea.com as the
    default target, but other deployments can be used via the 'api'
    parameter.

    In order to be able to use this command, a personal access token has to be
    generated on the platform (Account->Settings->Applications->Generate Token).

    .. versionadded:: 0.16
    """

    _params_ = _Gitea.create_sibling_params
    _params_['api']._doc = """\
        URL of the Gitea instance without a 'api/<version>' suffix"""

    @staticmethod
    @datasetmethod(name='create_sibling_gitea')
    @eval_results
    def __call__(
            reponame,
            *,
            dataset=None,
            recursive=False,
            recursion_limit=None,
            name='gitea',
            existing='error',
            api='https://gitea.com',
            credential=None,
            access_protocol='https',
            publish_depends=None,
            private=False,
            dry_run=False):

        yield from _create_sibling(
            platform=_Gitea(
                api,
                credential,
                require_token=not dry_run,
                token_info=f'Visit {api}/user/settings/applications '
                           'to create a token'),
            reponame=reponame,
            dataset=dataset,
            recursive=recursive,
            recursion_limit=recursion_limit,
            name=name,
            existing=existing,
            access_protocol=access_protocol,
            publish_depends=publish_depends,
            private=private,
            dry_run=dry_run,
        )
