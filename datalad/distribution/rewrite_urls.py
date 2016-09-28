# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""High-level interface for modifying URLs of subdatasets

"""

__docformat__ = 'restructuredtext'


import logging

from os.path import join as opj
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureStr, EnsureNone
from datalad.support.gitrepo import GitRepo
from datalad.interface.base import Interface
from datalad.distribution.dataset import Dataset, EnsureDataset, \
    datasetmethod, require_dataset

lgr = logging.getLogger('datalad.distribution.rewrite_urls')


def get_module_parser(repo):

    from git import GitConfigParser
    gitmodule_path = opj(repo.path, ".gitmodules")
    # TODO: What does constructor of GitConfigParser, in case file doesn't exist?
    #if exists(gitmodule_path):
    parser = GitConfigParser(gitmodule_path)
    parser.read()
    return parser


class RewriteURLs(Interface):
    """Rewrite the URLs of sub-datasets of a dataset
    """

    _params_ = dict(
        url=Parameter(
            args=("url",),
            doc="a template for building the URLs of the subdatasets "
                "List of currently available placeholders:\n"
                "%%NAME\tthe name of the subdataset, where slashes are replaced by "
                "dashes",
            constraints=EnsureStr()),
        dataset=Parameter(
            args=("-d", "--dataset",),
            doc="""specify the dataset to update.  If
            no dataset is given, an attempt is made to identify the dataset
            based on the current working directory""",
            constraints=EnsureDataset() | EnsureNone()),
        recursive=Parameter(
            args=("-r", "--recursive"),
            action="store_true",
            doc="recursively modify all subdataset URLs of `dataset` "),)

    # TODO: User interaction. Allow for skipping and editing on a per
    # subdataset basis. Therefore some --mode option (see below). Additionally,
    # this leads to URL being optional, so no URL given means to
    # edit per subdataset
    # mode=Parameter(
    #     args=("--mode",),
    #     doc="",
    #     constraints=EnsureChoice(["all", "ask"]),)

    @staticmethod
    @datasetmethod(name='rewrite_urls')
    def __call__(url, dataset=None, recursive=False):

        # shortcut
        ds = require_dataset(
            dataset, check_installed=True,
            purpose='modifying subdataset URLs')
        assert(ds.repo is not None)

        repos_to_update = [ds.repo]
        if recursive:
            repos_to_update += [GitRepo(opj(ds.path, sub_path))
                                for sub_path in
                                ds.get_subdatasets(recursive=True)]

        for dataset_repo in repos_to_update:
            parser = get_module_parser(dataset_repo)
            for submodule_section in parser.sections():
                submodule_name = submodule_section[11:-1]
                parser.set_value(submodule_section, "url",
                                 url.replace("%NAME",
                                             submodule_name.replace("/", "-")))

        return  # TODO: return value?
