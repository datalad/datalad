# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""High-level interface for dataset (component) publishing

"""

__docformat__ = 'restructuredtext'


import logging

from os import curdir
from os.path import join as opj, abspath, exists, relpath

from six import string_types
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureStr, EnsureNone, EnsureListOf
from datalad.support.gitrepo import GitRepo
from datalad.support.annexrepo import AnnexRepo, FileInGitError, \
    FileNotInAnnexError
from datalad.interface.base import Interface
from datalad.distribution.dataset import EnsureDataset, Dataset, \
    datasetmethod, resolve_path
from datalad.distribution.install import get_containing_subdataset
from datalad.cmd import CommandError
from datalad.utils import getpwd
from datalad.support.exceptions import InsufficientArgumentsError

lgr = logging.getLogger('datalad.distribution.publish')


class Publish(Interface):
    """Publish a dataset (e.g. to a web server)

    This makes the current state of a dataset available to a sibling of the
    dataset. That sibling needs to be known to the dataset before.
    `create_publication_target` commands are meant to set up such a sibling, but
    generally you can publish to any sibling added to a dataset.
    Publishing may or may not include subdatasets.
    By default file handles are published without their actual content,
    but they can be published including the content, of course.

    """
    # TODO: Figure out, how to tell about tracking branch/upstream
    #      (and the respective remote)
    #      - it is used, when no destination is given
    #      - it is configured to be the given destination, if there was no
    #        upstream set up before, so you can use just "datalad publish" next
    #        time.

    _params_ = dict(
        dataset=Parameter(
            args=("-d", "--dataset"),
            metavar='DATASET',
            doc="""specify the dataset to publish. If no dataset is given, an
            attempt is made to identify the dataset based on the current
            working directory""",
            constraints=EnsureDataset() | EnsureNone()),
        dest=Parameter(
            args=("dest",),
            metavar='DEST',
            doc="""sibling name identifying the publication target. If no
            destination is given an attempt is made to identify the target based
            on the dataset's configuration.""",
            # TODO: See TODO at top of class!
            nargs="?",
            constraints=EnsureStr() | EnsureNone()),
        recursive=Parameter(
            args=("-r", "--recursive"),
            action="store_true",
            doc="recursively publish all subdatasets of the dataset"),
        with_data=Parameter(
            args=("--with-data",),
            metavar='PATH',
            doc="path(s) to file handle(s) to publish including their actual "
                "content",
            constraints=EnsureListOf(string_types) | EnsureNone(),
            nargs='*'),)

    @staticmethod
    @datasetmethod(name='publish')
    def __call__(dataset=None, dest=None, with_data=None, recursive=False):

        # shortcut
        ds = dataset

        if ds is not None and not isinstance(ds, Dataset):
            ds = Dataset(ds)

        if ds is None:
            # try CWD:
            dspath = GitRepo.get_toppath(getpwd())
            if not dspath:
                raise InsufficientArgumentsError("No dataset found")
            ds = Dataset(dspath)

        assert(ds is not None)
        lgr.debug("Resolved dataset for publication: {0}".format(ds))

        # now, we know, we have to operate on ds. So, ds needs to be installed,
        # since we cannot publish anything from a not installed dataset,
        # can we?
        # (But may be just the existence of ds.repo is important here.)
        if not ds.is_installed():
            raise ValueError("No installed dataset found at "
                             "{0}.".format(ds.path))
        assert(ds.repo is not None)

        # Note: we need an upstream remote, if there's none given. We could
        # wait for git push to complain, but we need to explicitly figure it
        # out for pushing annex branch anyway and we might as well fail right
        # here.

        track_remote, track_branch = ds.repo.get_tracking_branch()

        # keep original dest in case it's None for passing to recursive calls:
        dest_resolved = dest
        if dest is None:
            if track_remote:
                dest_resolved = track_remote
            else:
                # we have no remote given and no upstream => fail
                raise InsufficientArgumentsError("No known default target for "
                                                 "publication and none given.")

        # upstream branch needed for update (merge) and subsequent push,
        # in case there is no.
        if track_branch is None:
            # no tracking branch yet:
            set_upstream = True
        else:
            set_upstream = False

        # is `dest` an already known remote?
        if dest_resolved not in ds.repo.get_remotes():
            # unknown remote
            raise ValueError("No sibling '%s' found." % dest_resolved)

        lgr.info("Publishing dataset {0} to sibling {1} "
                 "...".format(ds, dest_resolved))
        # we now know where to push to:
        ds.repo.push(remote=dest_resolved,
                     refspec=ds.repo.get_active_branch(),
                     set_upstream=set_upstream)
        # push annex branch:
        if isinstance(ds.repo, AnnexRepo):
            ds.repo.push(remote=dest_resolved,
                         refspec="+git-annex:git-annex")

        if with_data:
            lgr.info("Publishing data of dataset {0} ...".format(ds))
            for file_ in with_data:
                try:
                    subds = get_containing_subdataset(ds, file_)
                    lgr.debug("Resolved dataset for {0}: {1}".format(file_,
                                                                     subds))
                except ValueError as e:
                    if "path {0} not in dataset.".format(file_) in str(e):
                        # file_ is not in ds; this might be an invalid item to
                        # publish or it belongs to a superdataset, which called
                        # us recursively, so we are not responsible for that
                        # item
                        # => just skip
                        subds = None
                        lgr.debug("No (sub)dataset found for item {0}".format(
                            file_))
                    else:
                        raise
                if subds and subds == ds:
                    # we want to annex copy file_
                    # are we able to?
                    # What do we need to check
                    # (not in annex, is a directory, ...)? When to skip or fail?
                    # What to spit out?
                    # For now just call annex copy and later care for how to
                    # deal with failing
                    if not isinstance(ds.repo, AnnexRepo):
                        raise RuntimeError(
                            "Cannot publish content of something, that is not "
                            "part of an annex. ({0})".format(file_))
                    else:
                        lgr.info("Publishing data of {0} ...".format(file_))
                        ds.repo.copy_to(file_, dest_resolved)

        if recursive:
            for path in ds.get_dataset_handles():
                Dataset(path).publish(dest=dest,
                                      with_data=with_data,
                                      recursive=recursive)


        # TODO:
        # return values
        #  - we now may have published a dataset as well as files
        #  - how to return and render?

