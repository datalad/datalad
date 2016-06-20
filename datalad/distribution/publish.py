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

from os.path import join as opj

from six import string_types
from datalad.interface.base import Interface
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureStr
from datalad.support.constraints import EnsureNone
from datalad.support.constraints import EnsureListOf
from datalad.support.gitrepo import GitRepo
from datalad.support.annexrepo import AnnexRepo
from datalad.support.exceptions import InsufficientArgumentsError
from datalad.utils import getpwd

from .dataset import EnsureDataset
from .dataset import Dataset
from .dataset import datasetmethod
from .install import get_containing_subdataset


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

    # TODO: Doc!

    _params_ = dict(
        dataset=Parameter(
            args=("-d", "--dataset"),
            metavar='DATASET',
            doc="""specify the dataset to publish. If no dataset is given, an
            attempt is made to identify the dataset based on the current
            working directory""",
            constraints=EnsureDataset() | EnsureNone()),
        to=Parameter(
            args=("--to",),
            metavar='DEST',
            doc="""sibling name identifying the publication target. If no
            destination is given an attempt is made to identify the target based
            on the dataset's configuration.""",
            # TODO: See TODO at top of class!
            constraints=EnsureStr() | EnsureNone()),
        recursive=Parameter(
            args=("-r", "--recursive"),
            action="store_true",
            doc="recursively publish all subdatasets of the dataset"),
        path=Parameter(
            args=("path",),
            metavar='PATH',
            doc="path(s), that may point to file handle(s) to publish including "
                "their actual content or to subdataset(s) to be published. If a "
                "file handle is published with its data, this implicitly means "
                "to also publish the (sub)dataset it belongs to.",
            constraints=EnsureStr() | EnsureNone(),
            nargs='*'),)

    @staticmethod
    @datasetmethod(name='publish')
    def __call__(dataset=None, to=None, path=None, recursive=False):

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

        # Note: This logic means, we have to be within a dataset or explicitly
        #       pass a dataset in order to call publish. Even if we don't want
        #       to publish this dataset itself, but subdataset(s) only.
        #       Since we need to resolve paths against a dataset, another
        #       approach would complicate the matter. Consider '-C' and
        #       '--dataset' options before complaining ;)
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

        # figure out, what to publish from what (sub)dataset:
        publish_this = False   # whether to publish `ds`
        publish_files = []     # which files to publish by `ds`

        expl_subs = set()      # subdatasets to publish explicitly
        publish_subs = dict()  # collect what to publish from subdatasets
        if recursive:
            for subds_path in ds.get_subdatasets():
                expl_subs.add(subds_path)

        if path is None:
            # publish `ds` itself
            publish_this = True
        else:
            for p in path:
                if p in ds.get_subdatasets():
                    # p is a subdataset, that needs to be published itself
                    expl_subs.add(p)
                else:
                    try:
                        d = get_containing_subdataset(ds, p)
                    except ValueError as e:
                        # p is not in ds => skip:
                        lgr.warning(str(e) + " - Skipped.")
                        continue
                    if d == ds:
                        # p needs to be published from ds
                        publish_this = True
                        publish_files.append(p)
                    else:
                        # p belongs to subds `d`
                        publish_subs[d.path]['dataset'] = d
                        publish_subs[d.path]['files'].append(p)

        results = []

        if publish_this:

            # Note: we need an upstream remote, if there's none given. We could
            # wait for git push to complain, but we need to explicitly figure it
            # out for pushing annex branch anyway and we might as well fail
            # right here.

            track_remote, track_branch = ds.repo.get_tracking_branch()

            # keep `to` in case it's None for passing to recursive calls:
            dest_resolved = to
            if to is None:
                if track_remote:
                    dest_resolved = track_remote
                else:
                    # we have no remote given and no upstream => fail
                    raise InsufficientArgumentsError(
                        "No known default target for "
                        "publication and none given.")

            # upstream branch needed for update (merge) and subsequent push,
            # in case there is no.
            if track_branch is None:
                # no tracking branch yet:
                set_upstream = True
            else:
                set_upstream = False

            # is `to` an already known remote?
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

            results.append(ds)

            if publish_files:
                if not isinstance(ds.repo, AnnexRepo):
                    raise RuntimeError(
                        "Cannot publish content of something, that is not "
                        "part of an annex. ({0})".format(ds))

                lgr.info("Publishing data of dataset {0} ...".format(ds))
                results += ds.repo.copy_to(publish_files, dest_resolved)

        for dspath in expl_subs:
            # these datasets need to be pushed regardless of additional paths
            # pointing inside them
            # due to API, this may not happen when calling publish with paths,
            # therefore force it.
            # TODO: There might be a better solution to avoid two calls of
            # publish() on the very same Dataset instance
            results += Dataset(dspath).publish(to=to, recursive=recursive)

        for d in publish_subs:
            # recurse into subdatasets
            results += publish_subs[d]['dataset'].publish(
                to=to,
                path=publish_subs[d]['files'],
                recursive=recursive)

        return results

    @staticmethod
    def result_renderer_cmdline(res):
        from datalad.ui import ui
        if not res:
            ui.message("Nothing was published")
            return
        msg = "{n} {obj} published:\n".format(
            obj='items were' if len(res) > 1 else 'item was',
            n=len(res))
        for item in res:
            if isinstance(item, Dataset):
                msg += "Dataset: %s\n" % item.path
            else:
                msg += "File: %s\n" % item
        ui.message(msg)


