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

from os.path import relpath

from ..interface.base import (
    build_doc,
    Interface,
)
from ..interface.common_opts import (
    recursion_flag,
    recursion_limit,
    publish_depends,
)
from ..support.param import Parameter
from ..support.constraints import (
    EnsureChoice,
    EnsureNone,
    EnsureStr,
)
from ..utils import (
    assure_list,
)
from .dataset import (
    datasetmethod,
    EnsureDataset,
    require_dataset,
)
from .siblings import Siblings

lgr = logging.getLogger('datalad.distribution.create_sibling_github')

# presently only implemented method to turn subdataset paths into Github
# compliant repository name suffixes
template_fx = lambda x: re.sub(r'\s+', '_', re.sub(r'[/\\]+', '-', x))


@build_doc
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
    :kbd:`git hub setup` (if no 2FA is used).
    """
    # XXX prevent common args from being added to the docstring
    _no_eval_results = True

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
        name=Parameter(
            args=('-s', '--name',),
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
        github_login=Parameter(
            args=('--github-login',),
            constraints=EnsureStr() | EnsureNone(),
            metavar='NAME',
            doc="""Github user name or access token"""),
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
            constraints=EnsureChoice('https', 'ssh'),
            doc="""Which access protocol/URL to configure for the sibling"""),
        publish_depends=publish_depends,
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
            name='github',
            existing='error',
            github_login=None,
            github_passwd=None,
            github_organization=None,
            access_protocol='https',
            publish_depends=None,
            dryrun=False):
        # this is an absolute leaf package, import locally to avoid
        # unnecessary dependencies
        from datalad.support.github_ import _make_github_repos

        # what to operate on
        ds = require_dataset(
            dataset, check_installed=True, purpose='create Github sibling')
        # gather datasets and essential info
        # dataset instance and mountpoint relative to the top
        toprocess = [(ds, '')]
        if recursive:
            for sub in ds.subdatasets(
                    fulfilled=None,  # we want to report on missing dataset in here
                    recursive=recursive,
                    recursion_limit=recursion_limit,
                    result_xfm='datasets'):
                if not sub.is_installed():
                    lgr.info('Ignoring unavailable subdataset %s', sub)
                    continue
                toprocess.append((sub, relpath(sub.path, start=ds.path)))

        # check for existing remote configuration
        filtered = []
        for d, mp in toprocess:
            if name in d.repo.get_remotes():
                if existing == 'error':
                    msg = '{} already has a configured sibling "{}"'.format(
                        d, name)
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

        if not filtered:
            # all skipped
            return []

        # actually make it happen on Github
        rinfo = _make_github_repos(
            github_login, github_passwd, github_organization, filtered,
            existing, access_protocol, dryrun)

        # lastly configure the local datasets
        for d, url, existed in rinfo:
            if not dryrun:
                # first make sure that annex doesn't touch this one
                # but respect any existing config
                ignore_var = 'remote.{}.annex-ignore'.format(name)
                if not ignore_var in d.config:
                    d.config.add(ignore_var, 'true', where='local')
                Siblings()(
                    'configure',
                    dataset=d,
                    name=name,
                    url=url,
                    recursive=False,
                    # TODO fetch=True, maybe only if one existed already
                    publish_depends=publish_depends)

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
                        args.name,
                        d))
