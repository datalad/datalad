# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
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

from datalad.interface.base import (
    build_doc,
    Interface,
)
from datalad.distribution.dataset import (
    datasetmethod,
)
from datalad.interface.utils import eval_results
from datalad.distributed.create_sibling_ghlike import (
    _create_sibling,
)
from datalad.distributed.create_sibling_gogs import (
    _GOGS,
)

lgr = logging.getLogger('datalad.distributed.create_sibling_gitea')


class _Gitea(_GOGS):
    name = 'gitea'
    fullname = 'Gitea'
    response_code_unauthorized = 401

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
        elif r.status_code == self.response_code_unauthorized:
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
    """Gitea
    """

    _params_ = _Gitea.create_sibling_params

    @staticmethod
    @datasetmethod(name='create_sibling_gitea')
    @eval_results
    def __call__(
            reponame,
            dataset=None,
            recursive=False,
            recursion_limit=None,
            name='gitea',
            existing='error',
            api='https://gitea.com',
            credential='gitea',
            access_protocol='https',
            publish_depends=None,
            private=False,
            dry_run=False):

        yield from _create_sibling(
            platform=_Gitea(api, credential, require_token=not dry_run),
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
