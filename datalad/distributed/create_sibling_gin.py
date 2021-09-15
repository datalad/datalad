# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""High-level interface for creating a publication target on a GIN instance
"""

import logging

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

lgr = logging.getLogger('datalad.distributed.create_sibling_gin')


class _GIN(_GOGS):
    name = 'gin'
    fullname = 'GIN'
    response_code_unauthorized = 401

    def normalize_repo_properties(self, response):
        """Normalize the essential response properties for the result record
        """
        return dict(
            reponame=response.get('name'),
            private=response.get('private'),
            # GIN reports the SSH URL as 'clone_url', but we need
            # a HTML URL (without .git suffix) for setting up a
            # type-git special remote (if desired)
            clone_url=response.get('html_url'),
            ssh_url=response.get('ssh_url'),
            html_url=response.get('html_url'),
        )

@build_doc
class CreateSiblingGin(Interface):
    """GIN
    """

    _params_ = _GIN.create_sibling_params

    @staticmethod
    @datasetmethod(name='create_sibling_gin')
    @eval_results
    def __call__(
            reponame,
            dataset=None,
            recursive=False,
            recursion_limit=None,
            name='gin',
            existing='error',
            api='https://gin.g-node.org',
            credential='gin',
            access_protocol='https-ssh',
            publish_depends=None,
            private=False,
            dry_run=False):

        yield from _create_sibling(
            platform=_GIN(api, credential, require_token=not dry_run),
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
