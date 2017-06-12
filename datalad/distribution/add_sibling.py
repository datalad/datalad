# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""[obsolete: use `siblings add`]
"""

__docformat__ = 'restructuredtext'


import logging

from collections import OrderedDict
from os.path import join as opj, basename
from os.path import relpath

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
from datalad.interface.common_opts import publish_by_default
from datalad.interface.common_opts import annex_wanted_opt
from datalad.interface.common_opts import annex_group_opt
from datalad.interface.common_opts import annex_groupwanted_opt
from datalad.interface.common_opts import inherit_opt
from datalad.distribution.dataset import EnsureDataset, Dataset, \
    datasetmethod, require_dataset
from datalad.support.exceptions import CommandError
from datalad.support.exceptions import InsufficientArgumentsError


lgr = logging.getLogger('datalad.distribution.add_sibling')


def _check_deps(repo, deps):
    """Check if all `deps` remotes are known to the `repo`

    Raises
    ------
    ValueError
      if any of the deps is an unknown remote
    """
    unknown_deps = set(assure_list(deps)).difference(repo.get_remotes())
    if unknown_deps:
        raise ValueError(
            'unknown sibling(s) specified as publication dependency: %s'
            % unknown_deps)


class AddSibling(Interface):
    """THIS COMMAND IS OBSOLETE: Use `siblings add`.

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
            args=('-s', '--name',),
            metavar='NAME',
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
        publish_by_default=publish_by_default,
        annex_wanted=annex_wanted_opt,
        annex_group=annex_group_opt,
        annex_groupwanted=annex_groupwanted_opt,
        inherit=inherit_opt
    )

    @staticmethod
    @datasetmethod(name='add_sibling')
    def __call__(url=None, name=None, dataset=None,
                 pushurl=None, recursive=False, fetch=False, force=False,
                 as_common_datasrc=None, publish_depends=None,
                 publish_by_default=None,
                 annex_wanted=None, annex_group=None, annex_groupwanted=None,
                 inherit=False):

        # TODO: Detect malformed URL and fail?

        # TODO: allow for no url if 'inherit' and deduce from the super ds
        #       create-sibling already does it -- generalize/use
        #  Actually we could even inherit/deduce name from the super by checking
        #  which remote it is actively tracking in current branch... but may be
        #  would be too much magic

        # XXX possibly fail if fetch is False and as_common_datasrc
        # not yet sure if that is an error
        if (url is None and pushurl is None):
            raise InsufficientArgumentsError(
                """insufficient information to add a sibling
                (needs at least a dataset, and a URL).""")
        if url is None:
            url = pushurl

        if not name:
            urlri = RI(url)
            # use the hostname as default remote name
            name = urlri.hostname
            lgr.debug(
                "No sibling name given, use URL hostname '%s' as sibling name",
                name)

        ds = require_dataset(dataset, check_installed=True,
                             purpose='sibling addition')
        assert(ds.repo is not None)

        _check_deps(ds.repo, publish_depends)

        ds_basename = basename(ds.path)
        repos = OrderedDict()
        repos[ds_basename] = {'repo': ds.repo}

        if recursive:
            for subds in ds.subdatasets(recursive=True, result_xfm='datasets'):
                lgr.debug("Adding sub-dataset %s for adding a sibling",
                          subds.path)
                if not subds.is_installed():
                    lgr.info("Skipping adding sibling for %s since it "
                             "is not installed", subds)
                    continue
                # MIH why not simply absolute paths?
                repos[ds_basename + '/' + relpath(subds.path, start=ds.path)] = {
                    #                repos[subds_name] = {
                    # MIH this next line is strange, why not subds.repo? why GitRepo?
                    'repo': GitRepo(subds.path, create=False)
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
        # and default pushes
        dfltvar = "remote.{}.push".format(name)

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

                if existing_url and \
                        repoinfo['url'].rstrip('/') != existing_url.rstrip('/') \
                        or (pushurl and existing_pushurl and
                            repoinfo['pushurl'].rstrip('/') !=
                            existing_pushurl.rstrip('/')) \
                        or (pushurl and not existing_pushurl) \
                        or (publish_depends and set(ds.config.get(depvar, [])) != set(publish_depends)):
                    conflicting.append(repo_name)

        if not force and conflicting:
            raise RuntimeError("Sibling '{0}' already exists with conflicting"
                               " settings for {1} dataset(s). {2}".format(
                                   name, len(conflicting), conflicting))

        successfully_added = list()
        for repo_name in repos:
            repoinfo = repos[repo_name]
            repo = repoinfo['repo']
            if repo_name in already_existing:
                if not force and \
                        repo_name not in conflicting \
                        and repo.get_remote_url(name) is not None:
                    lgr.debug("Skipping {0}. Nothing to do.".format(repo_name))
                    continue
                # rewrite url
                repo.set_remote_url(name, repoinfo['url'])
                fetchvar = 'remote.{}.fetch'.format(name)
                if fetchvar not in repo.config:
                    # place default fetch refspec in config
                    # same as `git remote add` would have added
                    repo.config.add(
                        fetchvar,
                        '+refs/heads/*:refs/remotes/{}/*'.format(name),
                        where='local')
            else:
                # add the remote
                repo.add_remote(name, repoinfo['url'])
            if pushurl:
                repo.set_remote_url(name, repoinfo['pushurl'], push=True)
            if fetch:
                # fetch the remote so we are up to date
                lgr.debug("Fetching sibling %s of %s", name, repo_name)
                repo.fetch(name)

            if inherit:
                # Adjust variables which we should inherit
                delayed_super = _DelayedSuper(repo)
                publish_depends = AddSibling._inherit_config_var(
                    delayed_super, depvar, publish_depends)
                publish_by_default = AddSibling._inherit_config_var(
                    delayed_super, dfltvar, publish_by_default)
                # Copy relevant annex settings for the sibling
                # makes sense only if current AND super are annexes, so it is
                # kinda a boomer, since then forbids having a super a pure git
                if isinstance(repo, AnnexRepo) \
                    and isinstance(delayed_super.repo, AnnexRepo):
                    if annex_wanted is None:
                        annex_wanted = AddSibling._inherit_annex_var(
                            delayed_super, name, 'wanted'
                        )
                    if annex_group is None:
                        # I think it might be worth inheritting group regardless what
                        # value is
                        #if annex_wanted in {'groupwanted', 'standard'}:
                        annex_group = AddSibling._inherit_annex_var(
                            delayed_super, name, 'group'
                        )
                    if annex_wanted == 'groupwanted' and annex_groupwanted is None:
                        # we better have a value for the expression for that group
                        annex_groupwanted = AddSibling._inherit_annex_var(
                            delayed_super, name, 'groupwanted'
                        )

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

            if publish_by_default:
                if dfltvar in ds.config:
                    ds.config.unset(dfltvar, where='local', reload=False)
                for refspec in assure_list(publish_by_default):
                    lgr.info(
                        'Configure additional default publication refspec "%s"',
                        refspec)
                    ds.config.add(dfltvar, refspec, 'local')
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
                if annex_wanted:
                    repo.set_wanted(name, annex_wanted)
                if annex_group:
                    repo.set_group(name, annex_group)
                if annex_groupwanted:
                    if not annex_group:
                        raise InsufficientArgumentsError(
                            "To set groupwanted, you need to provide annex_group option")
                    repo.set_groupwanted(annex_group, annex_groupwanted)

            successfully_added.append(repo_name)

        return successfully_added

    @staticmethod
    def _inherit_annex_var(ds, remote, cfgvar):
        var = getattr(ds.repo, 'get_%s' % cfgvar)(remote)
        if var:
            lgr.info("Inherited annex config from %s %s = %s",
                     ds, cfgvar, var)
        return var

    @staticmethod
    def _inherit_config_var(ds, cfgvar, var):
        if var is None:
            var = ds.config.get(cfgvar)
            if var:
                lgr.info(
                    'Inherited publish_depends from %s: %s',
                    ds, var)
        return var

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


class _DelayedSuper(object):
    """A helper to delay deduction on super dataset until needed

    But if asked and not found -- blow up
    """

    def __init__(self, repo):
        self._child_dataset = Dataset(repo.path)
        self._super = None

    def __str__(self):
        return str(self.super)

    @property
    def super(self):
        if self._super is None:
            # here we must analyze current_ds's super, not the super_ds
            self._super = self._child_dataset.get_superdataset()
            if not self._super:
                raise RuntimeError(
                    "Cannot determine super dataset for %s, thus "
                    "cannot inherit anything" % self._child_dataset
                )
        return self._super

    # Lean proxies going through .super
    @property
    def config(self):
        return self.super.config

    @property
    def repo(self):
        return self.super.repo
