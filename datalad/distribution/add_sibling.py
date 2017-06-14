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

from os.path import basename

from datalad.utils import assure_list
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureStr, EnsureNone
from datalad.support.network import RI
from ..interface.base import Interface
from datalad.interface.common_opts import publish_depends
from datalad.interface.common_opts import publish_by_default
from datalad.interface.common_opts import annex_wanted_opt
from datalad.interface.common_opts import annex_group_opt
from datalad.interface.common_opts import annex_groupwanted_opt
from datalad.interface.common_opts import inherit_opt
from datalad.distribution.dataset import EnsureDataset, \
    datasetmethod, require_dataset
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
            # TODO RF recursive no longer an option, adjust docs
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
                 pushurl=None,
                 publish_depends=None,
                 publish_by_default=None,
                 annex_wanted=None, annex_group=None, annex_groupwanted=None,
                 inherit=False):
        # TODO: Detect malformed URL and fail?

        # TODO: allow for no url if 'inherit' and deduce from the super ds
        #       create-sibling already does it -- generalize/use
        #  Actually we could even inherit/deduce name from the super by checking
        #  which remote it is actively tracking in current branch... but may be
        #  would be too much magic

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

        repo_name = basename(ds.path)
        repo_props = {'repo': ds.repo}

        # Note: This is copied from create_sibling
        # as it is the same logic as for its target_dir.
        # TODO: centralize and generalize template symbol handling
        # TODO: Check pushurl for template symbols too. Probably raise if only
        #       one of them uses such symbols

        replicate_local_structure = "%NAME" not in url

        if not replicate_local_structure:
            repo_props['url'] = url.replace("%NAME",
                                            repo_name.replace("/", "-"))
            if pushurl:
                repo_props['pushurl'] = pushurl.replace("%NAME",
                                                        repo_name.replace("/",
                                                                          "-"))
        else:
            repo_props['url'] = url
            if pushurl:
                repo_props['pushurl'] = pushurl

        # define config var name for potential publication dependencies
        depvar = 'remote.{}.datalad-publish-depends'.format(name)

        # collect existing remotes:
        already_existing = list()
        conflicting = list()
        if name in ds.repo.get_remotes():
            already_existing.append(repo_name)
            lgr.debug("Remote '{0}' already exists "
                      "in '{1}'.""".format(name, repo_name))

            existing_url = ds.repo.get_remote_url(name)
            existing_pushurl = \
                ds.repo.get_remote_url(name, push=True)

            if existing_url and \
                    repo_props['url'].rstrip('/') != existing_url.rstrip('/') \
                    or (pushurl and existing_pushurl and
                        repo_props['pushurl'].rstrip('/') !=
                        existing_pushurl.rstrip('/')) \
                    or (pushurl and not existing_pushurl) \
                    or (publish_depends and set(ds.config.get(depvar, [])) != set(publish_depends)):
                conflicting.append(repo_name)

        if repo_name in already_existing:
            # rewrite url
            ds.repo.set_remote_url(name, repo_props['url'])
            fetchvar = 'remote.{}.fetch'.format(name)
            if fetchvar not in ds.repo.config:
                # place default fetch refspec in config
                # same as `git remote add` would have added
                ds.repo.config.add(
                    fetchvar,
                    '+refs/heads/*:refs/remotes/{}/*'.format(name),
                    where='local')
        else:
            # add the remote
            ds.repo.add_remote(name, repo_props['url'])
        if pushurl:
            ds.repo.set_remote_url(name, repo_props['pushurl'], push=True)

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


# TODO: RF nicely, test, make clear how different from urljoin etc
def _urljoin(base, url):
    return base + url if (base.endswith('/') or url.startswith('/')) else base + '/' + url


