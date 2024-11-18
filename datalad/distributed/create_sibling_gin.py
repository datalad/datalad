# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""High-level interface for creating a publication target on a GIN instance
"""

import logging

from datalad.distributed.create_sibling_ghlike import _create_sibling
from datalad.distributed.create_sibling_gogs import _GOGS
from datalad.distribution.dataset import (
    Dataset,
    datasetmethod,
)
from datalad.interface.base import (
    Interface,
    build_doc,
    eval_results,
)
from datalad.support.annexrepo import AnnexRepo

lgr = logging.getLogger('datalad.distributed.create_sibling_gin')


class _GIN(_GOGS):
    """Customizations for GIN as a GH-like platform
    """
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
    """Create a dataset sibling on a GIN site (with content hosting)

    GIN (G-Node infrastructure) is a free data management system. It is a
    GitHub-like, web-based repository store and provides fine-grained access
    control to shared data. GIN is built on Git and git-annex, and can natively
    host DataLad datasets, including their data content!

    This command uses the main GIN instance at https://gin.g-node.org as the
    default target, but other deployments can be used via the 'api'
    parameter.

    An SSH key, properly registered at the GIN instance, is required for data
    upload via DataLad. Data download from public projects is also possible via
    anonymous HTTP.

    In order to be able to use this command, a personal access token has to be
    generated on the platform (Account->Your Settings->Applications->Generate
    New Token).

    This command can be configured with
    "datalad.create-sibling-ghlike.extra-remote-settings.NETLOC.KEY=VALUE" in
    order to add any local KEY = VALUE configuration to the created sibling in
    the local `.git/config` file. NETLOC is the domain of the Gin instance to
    apply the configuration for.
    This leads to a behavior that is equivalent to calling datalad's
    ``siblings('configure', ...)``||``siblings configure`` command with the
    respective KEY-VALUE pair after creating the sibling.
    The configuration, like any other, could be set at user- or system level, so
    users do not need to add this configuration to every sibling created with
    the service at NETLOC themselves.

    .. versionadded:: 0.16
    """

    _examples_ = [
        dict(text="Create a repo 'myrepo' on GIN and register it as sibling "
                  "'mygin'",
             code_py="create_sibling_gin('myrepo', name='mygin', dataset='.')",
             code_cmd="datalad create-sibling-gin myrepo -s mygin"),
        dict(text="Create private repos with name(-prefix) 'myrepo' on GIN "
                  "for a dataset and all its present subdatasets",
             code_py="create_sibling_gin('myrepo', dataset='.', "
                     "recursive=True, private=True)",
             code_cmd="datalad create-sibling-gin myrepo -r --private"),
        dict(text="Create a sibling repo on GIN, and register it as a "
                  "common data source in the dataset that is available "
                  "regardless of whether the dataset was directly cloned "
                  "from GIN",
             code_py="""\
                 > ds = Dataset('.')
                 > ds.create_sibling_gin('myrepo', name='gin')
                 # first push creates git-annex branch remotely and obtains annex UUID
                 > ds.push(to='gin')
                 > ds.siblings('configure', name='gin', as_common_datasrc='gin-storage')
                 # announce availability (redo for other siblings)
                 > ds.push(to='gin')
                 """,
             code_cmd="""\
                 % datalad create-sibling-gin myrepo -s gin
                 # first push creates git-annex branch remotely and obtains annex UUID
                 % datalad push --to gin
                 % datalad siblings configure -s gin --as-common-datasrc gin-storage
                 # announce availability (redo for other siblings)
                 % datalad push --to gin
                 """,
             ),
    ]

    _params_ = _GIN.create_sibling_params
    _params_['api']._doc = """\
        URL of the GIN instance without an 'api/<version>' suffix"""

    @staticmethod
    @datasetmethod(name='create_sibling_gin')
    @eval_results
    def __call__(
            reponame,
            *,
            dataset=None,
            recursive=False,
            recursion_limit=None,
            name='gin',
            existing='error',
            api='https://gin.g-node.org',
            credential=None,
            access_protocol='https-ssh',
            publish_depends=None,
            private=False,
            description=None,
            dry_run=False):

        for res in _create_sibling(
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
                description=description,
                dry_run=dry_run):
            if res.get('action') == 'configure-sibling' \
                    and res.get('annex-ignore') in ('true', True):
                # when we see that git-annex had disabled access to GIN
                # we will revert it for any dataset with an annex.
                # git-annex's conclusion might solely be based on the
                # fact that it tested prior the first push (failed to
                # obtain a git-annex branch with a UUID) and concluded
                # that there can never be an annex.
                # however, we know for sure that GIN can do it, so we
                # force this to enable correct subsequent data transfer
                ds = Dataset(res['path'])
                if isinstance(ds.repo, AnnexRepo):
                    ds.config.set(f'remote.{name}.annex-ignore', 'false',
                                  scope='local')
                    res['annex-ignore'] = 'false'
            yield res
