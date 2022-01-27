# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""High-level interface for creating a publication target on a GOGS instance
"""

import logging
from urllib.parse import urlparse

from datalad.distributed.create_sibling_ghlike import (
    _create_sibling,
    _GitHubLike,
)
from datalad.distribution.dataset import datasetmethod
from datalad.interface.base import (
    Interface,
    build_doc,
)
from datalad.interface.utils import eval_results

lgr = logging.getLogger('datalad.distributed.create_sibling_gogs')


class _GOGS(_GitHubLike):
    """Customizations for the GOGS platform"""
    name = 'gogs'
    fullname = 'GOGS'
    create_org_repo_endpoint = 'api/v1/org/{organization}/repos'
    create_user_repo_endpoint = 'api/v1/user/repos'
    get_authenticated_user_endpoint = 'api/v1/user'
    get_repo_info_endpoint = 'api/v1/repos/{user}/{repo}'
    extra_remote_settings = {
        # first make sure that annex doesn't touch this one
        # but respect any existing config
        'annex-ignore': 'true',
    }

    def __init__(self, url, credential, require_token=True, token_info=None):
        if not url:
            raise ValueError(f'API URL required for {self.fullname}')
        return super().__init__(
            url,
            credential,
            require_token=require_token,
            token_info=f'Visit {url}/user/settings/applications '
                       'to create a token')


@build_doc
class CreateSiblingGogs(Interface):
    """Create a dataset sibling on a GOGS site

    GOGS is a self-hosted, free and open source code hosting solution with
    low resource demands that enable running it on inexpensive devices like
    a Raspberry Pi, or even directly on a NAS device.

    In order to be able to use this command, a personal access token has to be
    generated on the platform
    (Account->Your Settings->Applications->Generate New Token).

    .. versionadded:: 0.16
    """

    _params_ = _GOGS.create_sibling_params
    _params_['api']._doc = """\
        URL of the GOGS instance without a 'api/<version>' suffix"""

    @staticmethod
    @datasetmethod(name='create_sibling_gogs')
    @eval_results
    def __call__(
            reponame,
            *,
            # possibly retrieve a default from config
            api=None,
            dataset=None,
            recursive=False,
            recursion_limit=None,
            name=None,
            existing='error',
            credential=None,
            access_protocol='https',
            publish_depends=None,
            private=False,
            dry_run=False):

        yield from _create_sibling(
            platform=_GOGS(api, credential, require_token=not dry_run),
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
