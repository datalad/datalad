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
        sibling=Parameter(
            args=('sibling',),
            doc="""Name of the sibling to be added. If RECURSIVE is set, the
                same name will be used to address the subdatasets' siblings""",
            constraints=EnsureStr() | EnsureNone()),
        url=Parameter(
            args=('url',),
            doc="""The URL of or path to the dataset sibling named by
                `sibling`.
                If you want to recursively add siblings, it is expected, that
                you pass a template for building the URLs of the siblings of
                all (sub)datasets by using placeholders.\n
                List of currently available placeholders:\n
                %%NAME\tthe name of the dataset, where slashes are replaced by
                dashes.\nThis option is ignored if there is already a
                configured sibling dataset under the name given by `sibling`""",
            constraints=EnsureStr() | EnsureNone()),
        pushurl=Parameter(
            args=('--pushurl',),
            doc="""In case the `url` cannot be used to publish to the dataset
                sibling, this option specifies a URL to be used instead.\n
                This option is ignored if there is already a configured sibling
                dataset under the name given by `sibling`""",
            constraints=EnsureStr() | EnsureNone()),
        recursive=Parameter(
            args=("--recursive", "-r"),
            action="store_true",
            doc="""Recursively add the `sibling` to all subdatasets of
                `dataset`""",),
        force=Parameter(
            args=("--force", "-f",),
            action="store_true",
            doc="""If `sibling` exists already, force to (re-)configure its
                URLs""",),)

    @staticmethod
    @datasetmethod(name='add_sibling')
    def __call__(dataset=None, sibling=None, url=None,
                 pushurl=None, recursive=False, force=False):

        # TODO: Detect malformed URL and fail?

        if sibling is None or url is None:
            raise ValueError("""insufficient information to add a sibling
                (needs at least a dataset, a name and an URL).""")

        # shortcut
        ds = dataset

        if ds is not None and not isinstance(ds, Dataset):
            ds = Dataset(ds)
        if ds is None:
            # try to find a dataset at or above CWD
            dspath = GitRepo.get_toppath(abspath(getpwd()))
            if dspath is None:
                raise ValueError("""No dataset found
                                 at or above {0}.""".format(getpwd()))
            ds = Dataset(dspath)
            lgr.debug("Resolved dataset for target creation: {0}".format(ds))

        assert(ds is not None and sibling is not None and url is not None)

        if not ds.is_installed():
            raise ValueError("""Dataset {0} is not installed yet.""".format(ds))
        assert(ds.repo is not None)

        repos = dict()
        repos[basename(ds.path)] = ds.repo
        if recursive:
            for subds in ds.get_dataset_handles(recursive=True):
                sub_path = opj(ds.path, subds)
                repos[basename(ds.path) + '/' + subds] = \
                    GitRepo(sub_path, create=False)

        # collect existing remotes:
        already_existing = list()
        conflicting = list()
        for repo in repos:
            # TODO: Add the following to repos dict? Need it again later on.
            REPO_NAME = repo.replace("/", "-")
            REPO_URL = url.replace("%NAME", REPO_NAME)
            if pushurl:
                REPO_PUSHURL = pushurl.replace("%NAME", REPO_NAME)

            if sibling in repos[repo].git_get_remotes():
                already_existing.append(repo)
                lgr.debug("""Remote '{0}' already exists
                          in '{1}'.""".format(sibling, repo))
                if REPO_URL != repos[repo].git_get_remote_url(sibling) or \
                    (pushurl and
                        REPO_PUSHURL != repos[repo].git_get_remote_url(
                                sibling, push=True)):
                    conflicting.append(repo)

        if not force and conflicting:
            raise RuntimeError("""Sibling '{0}' already exists with conflicting
                               URL for {1} dataset(s). {2}""".format(
                sibling, len(conflicting), conflicting))

        runner = Runner()
        successfully_added = list()
        for repo in repos:
            # template replacing:
            # %NAME:
            REPO_NAME = repo.replace("/", "-")

            if repo in already_existing:
                if repo not in conflicting:
                    lgr.debug("Skipping {0}. Nothing to do.".format(repo))
                    continue
                # rewrite url
                cmd = ["git", "remote", "set-url", sibling, url.replace("%NAME", REPO_NAME)]
                runner.run(cmd, cwd=repos[repo].path)
            else:
                # add the remote
                cmd = ["git", "remote", "add", sibling,
                       url.replace("%NAME", REPO_NAME)]
                runner.run(cmd, cwd=repos[repo].path)
            if pushurl:
                cmd = ["git", "remote", "set-url", "--push", sibling,
                       pushurl.replace("%NAME", REPO_NAME)]
                runner.run(cmd, cwd=repos[repo].path)
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
            ds='{n} datasets'.format(len(res))
            if len(res) > 1 else 'one dataset',
            items=items)
        ui.message(msg)
