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

from os.path import join as opj, abspath, basename
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureStr, EnsureNone
from datalad.support.gitrepo import GitRepo
from datalad.cmd import Runner
from ..interface.base import Interface
from datalad.distribution.dataset import EnsureDataset, Dataset, datasetmethod
from datalad.utils import getpwd


lgr = logging.getLogger('datalad.distribution.add_publication_target')


class AddSibling(Interface):
    """Adds a sibling to a dataset."""

    _params_ = dict(
        # TODO: Somehow the replacement of '_' and '-' is buggy on
        # positional arguments
        dataset=Parameter(
            args=("--dataset", "-d",),
            doc="""specify the dataset to add the sibling to. If
                no dataset is given, an attempt is made to identify the dataset
                based on the current working directory""",
            constraints=EnsureDataset() | EnsureNone()),
        name=Parameter(
            args=('name',),
            doc="""Name of the sibling to be added. If RECURSIVE is set, the
                same name will be used to address the subdatasets' siblings""",
            constraints=EnsureStr() | EnsureNone()),
        url=Parameter(
            args=('url',),
            doc="""The URL of or path to the dataset sibling named by
                `name`.
                If you want to recursively add siblings, it is expected, that
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
            doc="""In case the `url` cannot be used to publish to the dataset
                sibling, this option specifies a URL to be used instead.\nIf no
                `url` is given, `pushurl` serves as `url` as well.
                This option is ignored if there is already a configured sibling
                dataset under the name given by `name`""",
            constraints=EnsureStr() | EnsureNone()),
        recursive=Parameter(
            args=("--recursive", "-r"),
            action="store_true",
            doc="""Recursively add the sibling `name` to all subdatasets of
                `dataset`""",),
        force=Parameter(
            args=("--force", "-f",),
            action="store_true",
            doc="""If sibling `name` exists already, force to (re-)configure its
                URLs""",),)

    @staticmethod
    @datasetmethod(name='add_sibling')
    def __call__(dataset=None, name=None, url=None,
                 pushurl=None, recursive=False, force=False):

        # TODO: Detect malformed URL and fail?

        if name is None or (url is None and pushurl is None):
            raise ValueError("""insufficient information to add a sibling
                (needs at least a dataset, a name and an URL).""")
        if url is None:
            url = pushurl

        # shortcut
        ds = dataset

        if ds is not None and not isinstance(ds, Dataset):
            ds = Dataset(ds)
        if ds is None:
            # try to find a dataset at or above CWD
            dspath = GitRepo.get_toppath(abspath(getpwd()))
            if dspath is None:
                raise ValueError(
                        "No dataset found at or above {0}.".format(getpwd()))
            ds = Dataset(dspath)
            lgr.debug("Resolved dataset for target creation: {0}".format(ds))

        assert(ds is not None and name is not None and url is not None)

        if not ds.is_installed():
            raise ValueError("Dataset {0} is not installed yet.".format(ds))
        assert(ds.repo is not None)

        ds_basename = basename(ds.path)
        repos = {
            ds_basename: {'repo': ds.repo}
        }
        if recursive:
            for subds in ds.get_dataset_handles(recursive=True):
                sub_path = opj(ds.path, subds)
                repos[ds_basename + '/' + subds] = {
#                repos[subds] = {
                    'repo': GitRepo(sub_path, create=False)
                }

        # Note: This is copied from create_publication_target_sshwebserver
        # as it is the same logic as for its target_dir.
        # TODO: centralize and generalize template symbol handling
        # TODO: Check pushurl for template symbols too. Probably raise if only
        #       one of them uses such symbols

        replicate_local_structure = False
        if "%NAME" not in url:
            replicate_local_structure = True

        for repo in repos:
            if not replicate_local_structure:
                repos[repo]['url'] = url.replace("%NAME",
                                                 repo.replace("/", "-"))
                if pushurl:
                    repos[repo]['pushurl'] = pushurl.replace("%NAME",
                                                             repo.replace("/",
                                                                          "-"))
            else:
                repos[repo]['url'] = url
                if pushurl:
                    repos[repo]['pushurl'] = pushurl

                if repo != ds_basename:
                    repos[repo]['url'] = _urljoin(repos[repo]['url'], repo[len(ds_basename)+1:])
                    if pushurl:
                        repos[repo]['pushurl'] = _urljoin(repos[repo]['pushurl'], repo[len(ds_basename)+1:])

        # collect existing remotes:
        already_existing = list()
        conflicting = list()
        for repo in repos:
            if name in repos[repo]['repo'].git_get_remotes():
                already_existing.append(repo)
                lgr.debug("""Remote '{0}' already exists
                          in '{1}'.""".format(name, repo))

                existing_url = repos[repo]['repo'].git_get_remote_url(name)
                existing_pushurl = \
                    repos[repo]['repo'].git_get_remote_url(name, push=True)

                if repos[repo]['url'].rstrip('/') != existing_url.rstrip('/') \
                        or (pushurl and existing_pushurl and
                            repos[repo]['pushurl'].rstrip('/') !=
                                    existing_pushurl.rstrip('/')) \
                        or (pushurl and not existing_pushurl):
                    conflicting.append(repo)

        if not force and conflicting:
            raise RuntimeError("Sibling '{0}' already exists with conflicting"
                               " URL for {1} dataset(s). {2}".format(
                                   name, len(conflicting), conflicting))

        runner = Runner()
        successfully_added = list()
        for repo in repos:
            if repo in already_existing:
                if repo not in conflicting:
                    lgr.debug("Skipping {0}. Nothing to do.".format(repo))
                    continue
                # rewrite url
                cmd = ["git", "remote", "set-url", name, repos[repo]['url']]
                runner.run(cmd, cwd=repos[repo]['repo'].path)
            else:
                # add the remote
                cmd = ["git", "remote", "add", name, repos[repo]['url']]
                runner.run(cmd, cwd=repos[repo]['repo'].path)
            if pushurl:
                cmd = ["git", "remote", "set-url", "--push", name,
                       repos[repo]['pushurl']]
                runner.run(cmd, cwd=repos[repo]['repo'].path)
            successfully_added.append(repo)

        return successfully_added

    @staticmethod
    def result_renderer_cmdline(res):
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