# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""High-level interface for adding a sibling to a dataset
"""

__docformat__ = 'restructuredtext'


import logging

from collections import OrderedDict
from os.path import join as opj, basename

from datalad.utils import assure_list
from datalad.dochelpers import exc_str
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureStr, EnsureNone, EnsureBool
from datalad.support.gitrepo import GitRepo
from datalad.support.annexrepo import AnnexRepo
from datalad.support.network import RI
from datalad.support.network import URL
from ..interface.base import Interface
from datalad.interface.common_opts import recursion_flag
from datalad.interface.common_opts import as_common_datasrc
from datalad.interface.common_opts import publish_depends
from datalad.distribution.dataset import EnsureDataset, Dataset, \
    datasetmethod, require_dataset
from datalad.support.exceptions import CommandError


lgr = logging.getLogger('datalad.distribution.add_publication_target')


class AddSibling(Interface):
    """Add a sibling to a dataset.

    """

    _params_ = dict(
        # TODO: Somehow the replacement of '_' and '-' is buggy on
        # positional arguments
        dataset=Parameter(
            args=("--dataset", "-d",),
            doc="""specify the dataset to add the sibling to.  If
                no dataset is given, an attempt is made to identify the dataset
                based on the current working directory""",
            constraints=EnsureDataset() | EnsureNone()),
        name=Parameter(
            args=('name',),
            doc="""name of the sibling to be added.  If RECURSIVE is set, the
                same name will be used to address the subdatasets' siblings""",
            constraints=EnsureStr() | EnsureNone()),
        url=Parameter(
            args=('url',),
            doc="""the URL of or path to the dataset sibling named by
                `name`.  If you want to recursively add siblings, it is expected, that
                you pass a template for building the URLs of the siblings of
                all (sub)datasets by using placeholders.\n
                List of currently available placeholders:\n
                %%NAME\tthe name of the dataset, where slashes are replaced by
                dashes.\nThis option is ignored if there is already a
                configured sibling dataset under the name given by `name`""",
            constraints=EnsureStr() | EnsureNone(),
            nargs="?"),
        pushurl=Parameter(
            args=('--pushurl',),
            doc="""in case the `url` cannot be used to publish to the dataset
                sibling, this option specifies a URL to be used instead.\nIf no
                `url` is given, `pushurl` serves as `url` as well.
                This option is ignored if there is already a configured sibling
                dataset under the name given by `name`""",
            constraints=EnsureStr() | EnsureNone()),
        recursive=recursion_flag,
        fetch=Parameter(
            args=("--fetch",),
            action="store_true",
            doc="""fetch the sibling after adding"""),
        force=Parameter(
            args=("--force", "-f",),
            action="store_true",
            doc="""if sibling `name` exists already, force to (re-)configure its
                URLs""",),
        as_common_datasrc=as_common_datasrc,
        publish_depends=publish_depends,
    )

    @staticmethod
    @datasetmethod(name='add_sibling')
    def __call__(name=None, url=None, dataset=None,
                 pushurl=None, recursive=False, fetch=False, force=False,
                 as_common_datasrc=None, publish_depends=None):

        # TODO: Detect malformed URL and fail?

        # XXX possibly fail if fetch is False and as_common_datasrc
        # not yet sure if that is an error
        if name is None or (url is None and pushurl is None):
            raise ValueError("""insufficient information to add a sibling
                (needs at least a dataset, a name and an URL).""")
        if url is None:
            url = pushurl

        ds = require_dataset(dataset, check_installed=True,
                             purpose='sibling addition')
        assert(ds.repo is not None)

        ds_basename = basename(ds.path)
        repos = OrderedDict()
        repos[ds_basename] = {'repo': ds.repo}

        if recursive:
            for subds_name in ds.get_subdatasets(recursive=True):
                subds_path = opj(ds.path, subds_name)
                subds = Dataset(subds_path)
                lgr.debug("Adding sub-dataset %s for adding a sibling",
                          subds_path)
                if not subds.is_installed():
                    lgr.info("Skipping adding sibling for %s since it "
                             "is not installed", subds)
                    continue
                repos[ds_basename + '/' + subds_name] = {
                    #                repos[subds_name] = {
                    'repo': GitRepo(subds_path, create=False)
                }

        # Note: This is copied from create_sibling
        # as it is the same logic as for its target_dir.
        # TODO: centralize and generalize template symbol handling
        # TODO: Check pushurl for template symbols too. Probably raise if only
        #       one of them uses such symbols

        replicate_local_structure = "%NAME" not in url

        for repo_name in repos:
            repo = repos[repo_name]
            if not replicate_local_structure:
                repo['url'] = url.replace("%NAME",
                                           repo_name.replace("/", "-"))
                if pushurl:
                    repo['pushurl'] = pushurl.replace("%NAME",
                                                       repo_name.replace("/",
                                                                          "-"))
            else:
                repo['url'] = url
                if pushurl:
                    repo['pushurl'] = pushurl

                if repo_name != ds_basename:
                    repo['url'] = _urljoin(repo['url'], repo_name[len(ds_basename) + 1:])
                    if pushurl:
                        repo['pushurl'] = _urljoin(repo['pushurl'], repo_name[len(ds_basename) + 1:])

        # define config var name for potential publication dependencies
        depvar = 'remote.{}.datalad-publish-depends'.format(name)

        # collect existing remotes:
        already_existing = list()
        conflicting = list()
        for repo_name in repos:
            repoinfo = repos[repo_name]
            repo = repoinfo['repo']
            if name in repo.get_remotes():
                already_existing.append(repo_name)
                lgr.debug("Remote '{0}' already exists "
                          "in '{1}'.""".format(name, repo_name))

                existing_url = repo.get_remote_url(name)
                existing_pushurl = \
                    repo.get_remote_url(name, push=True)

                if (not existing_url or repoinfo['url'].rstrip('/') != existing_url.rstrip('/')) \
                        or (pushurl and existing_pushurl and
                            repoinfo['pushurl'].rstrip('/') !=
                                    existing_pushurl.rstrip('/')) \
                        or (pushurl and not existing_pushurl) \
                        or (publish_depends and set(ds.config.get(depvar, [])) != set(publish_depends)):
                    conflicting.append(repo_name)

        if not force and conflicting:
            raise RuntimeError("Sibling '{0}' already exists with conflicting"
                               " URL for {1} dataset(s). {2}".format(
                                   name, len(conflicting), conflicting))

        successfully_added = list()
        for repo_name in repos:
            repoinfo = repos[repo_name]
            repo = repoinfo['repo']
            if repo_name in already_existing:
                if repo_name not in conflicting:
                    lgr.debug("Skipping {0}. Nothing to do.".format(repo_name))
                    continue
                # rewrite url
                repo.set_remote_url(name, repoinfo['url'])
            else:
                # add the remote
                repo.add_remote(name, repoinfo['url'])
            if pushurl:
                repo.set_remote_url(name, repoinfo['pushurl'], push=True)
            if fetch:
                # fetch the remote so we are up to date
                lgr.debug("Fetching sibling %s of %s", name, repo_name)
                repo.fetch(name)

            if publish_depends:
                if depvar in ds.config:
                    # config vars are incremental, so make sure we start from
                    # scratch
                    ds.config.unset(depvar, where='local', reload=False)
                for d in assure_list(publish_depends):
                    lgr.info(
                        'Configure additional publication dependency on "%s"',
                        d)
                    ds.config.add(depvar, d, where='local', reload=False)
                ds.config.reload()

            assert isinstance(repo, GitRepo)  # just against silly code
            if isinstance(repo, AnnexRepo):
                # we need to check if added sibling an annex, and try to enable it
                # another part of the fix for #463 and #432
                try:
                    if not ds.config.obtain(
                            'remote.{}.annex-ignore'.format(name),
                            default=False,
                            valtype=EnsureBool(),
                            store=False):
                        repo.enable_remote(name)
                except CommandError as exc:
                    lgr.info("Failed to enable annex remote %s, "
                             "could be a pure git" % name)
                    lgr.debug("Exception was: %s" % exc_str(exc))
                if as_common_datasrc:
                    ri = RI(repoinfo['url'])
                    if isinstance(ri, URL) and ri.scheme in ('http', 'https'):
                        # XXX what if there is already a special remote
                        # of this name? Above check for remotes ignores special
                        # remotes. we need to `git annex dead REMOTE` on reconfigure
                        # before we can init a new one
                        # XXX except it is not enough

                        # make special remote of type=git (see #335)
                        repo._run_annex_command(
                            'initremote',
                            annex_options=[
                                as_common_datasrc,
                                'type=git',
                                'location={}'.format(repoinfo['url']),
                                'autoenable=true'])
                    else:
                        lgr.warning(
                            'Not configuring "%s" as a common data source, '
                            'URL protocol is not http or https',
                            name)
            successfully_added.append(repo_name)

        return successfully_added

    @staticmethod
    def result_renderer_cmdline(res, args):
        from datalad.ui import ui
        if res is None:
            res = []
        if not isinstance(res, list):
            res = [res]
        if not len(res):
            ui.message("No sibling was added")
            return
        items= '\n'.join(map(str, res))
        msg = "Added sibling to {ds}:\n{items}".format(
            ds='{} datasets'.format(len(res))
            if len(res) > 1
            else 'one dataset',
            items=items)
        ui.message(msg)

# TODO: RF nicely, test, make clear how different from urljoin etc
def _urljoin(base, url):
    return base + url if (base.endswith('/') or url.startswith('/')) else base + '/' + url
