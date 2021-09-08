# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""High-level interface for creating a publication target on a GOGS instance
"""

import logging
from urllib.parse import (
    urlparse,
)

from datalad.interface.base import (
    build_doc,
    Interface,
)
from datalad.distribution.dataset import (
    datasetmethod,
)
from datalad.interface.utils import eval_results
from datalad.distributed.create_sibling_ghlike import (
    _GitHubLike,
    _create_sibling,
)

lgr = logging.getLogger('datalad.distributed.create_sibling_gogs')


class _GOGS(_GitHubLike):
    name = 'gogs'
    fullname = 'GOGS'
    create_org_repo_endpoint = 'api/v1/org/{organization}/repos'
    create_user_repo_endpoint = 'api/v1/user/repos'
    get_authenticated_user_endpoint = 'api/v1/user'
    get_repo_info_endpoint = 'api/v1/repos/{user}/{repo}'

    def __init__(self, url, credential, require_token=True):
        if not url:
            raise ValueError(f'API URL required for {self.fullname}')
        if credential is None:
            credential = urlparse(url).netloc
        return super().__init__(url, credential, require_token=require_token)


@build_doc
class CreateSiblingGogs(Interface):
    """GOGS
    """

    _params_ = _GOGS.create_sibling_params
    _params_['api']._doc = """\
        URL of the GOGS instance without a 'api/<version>' suffix"""

    @staticmethod
    @datasetmethod(name='create_sibling_gogs')
    @eval_results
    def __call__(
            reponame,
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
