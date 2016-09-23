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

import logging

from os.path import join as opj

from six import string_types
from datalad.interface.base import Interface
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureStr
from datalad.support.constraints import EnsureNone
from datalad.support.constraints import EnsureChoice
from datalad.support.annexrepo import AnnexRepo
from datalad.support.exceptions import InsufficientArgumentsError
from datalad.dochelpers import exc_str
from datalad.utils import assure_list

from .dataset import EnsureDataset
from .dataset import Dataset
from .dataset import datasetmethod
from .dataset import require_dataset

__docformat__ = 'restructuredtext'

lgr = logging.getLogger('datalad.distribution.publish')


def _log_push_info(pi_list):
    from git.remote import PushInfo as PI

    if pi_list:
        for push_info in pi_list:
            if (push_info.flags & PI.ERROR) == PI.ERROR:
                lgr.error(push_info.summary)
            else:
                lgr.info(push_info.summary)
    else:
        lgr.warning("Nothing was pushed.")


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
            on the dataset's configuration""",
            # TODO: See TODO at top of class!
            constraints=EnsureStr() | EnsureNone()),
        recursive=Parameter(
            args=("-r", "--recursive"),
            action="store_true",
            doc="recursively publish all subdatasets of the dataset. In order "
                "to recursively publish with all data, use '.' as `path` in "
                "combination with `recursive`"),
        since=Parameter(
            args=("--since",),
            constraints=EnsureStr() | EnsureNone(),
            doc="""When publishing dataset(s), specifies commit (treeish, tag, etc)
            from which to look for changes
            to decide either updated publishing is necessary for this and which children.
            If empty argument is provided, then we will always run publish command.
            By default, would take from the previously published to that remote/sibling
            state (for the current branch)"""),
        skip_failing=Parameter(
            args=("--skip-failing",),
            action="store_true",
            doc="skip failing sub-datasets (incombination with `recursive`) "
                "instead of failing altogether"),
        path=Parameter(
            args=("path",),
            metavar='PATH',
            doc="path(s), that may point to file handle(s) to publish including "
                "their actual content or to subdataset(s) to be published. If a "
                "file handle is published with its data, this implicitly means "
                "to also publish the (sub)dataset it belongs to. '.' as a path "
                "is treated in a special way in the sense, that it is passed "
                "to subdatasets in case `recursive` is also given.",
            constraints=EnsureStr() | EnsureNone(),
            nargs='*'),
        annex_copy_opts=Parameter(
            args=("--annex-copy-opts",),
            metavar='OPT_STR',  # better name?
            doc="options passed to 'annex copy'",
            constraints=EnsureStr() | EnsureNone(),))

    @staticmethod
    @datasetmethod(name='publish')
    def __call__(path=None, dataset=None, to=None, recursive=False, since=None,
                 skip_failing=False, annex_copy_opts=None):
        ds = require_dataset(dataset, check_installed=True, purpose='publication')
        assert(ds.repo is not None)

        path = assure_list(path)

        # figure out, what to publish from what (sub)dataset:
        publish_this = False   # whether to publish `ds`
        publish_files = []     # which files to publish by `ds`

        expl_subs = set()      # subdatasets to publish explicitly
        publish_subs = dict()  # collect what to publish from subdatasets

        if not path:
            # publish `ds` itself, if nothing else is given:
            publish_this = True
        else:
            for p in path:
                subdatasets = ds.get_subdatasets()
                if p in subdatasets:
                    # p is a subdataset, that needs to be published itself
                    expl_subs.add(p)
                else:
                    try:
                        d = ds.get_containing_subdataset(p)
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
                        if not publish_subs[d.path]:
                            publish_subs[d.path] = dict()
                        if not publish_subs[d.d.path]['files']:
                            publish_subs[d.d.path]['files'] = list()
                        publish_subs[d.path]['dataset'] = d
                        publish_subs[d.path]['files'].append(p)

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

        subds_prev_hexsha = {}
        if recursive:
            all_subdatasets = ds.get_subdatasets(fulfilled=True)
            subds_to_consider = \
                Publish._get_changed_datasets(
                    ds.repo, all_subdatasets, dest_resolved, since=since) \
                if publish_this \
                else all_subdatasets
            # if we were returned a dict, we got subds_prev_hexsha
            if isinstance(subds_to_consider, dict):
                subds_prev_hexsha = subds_to_consider
            for subds_path in subds_to_consider:
                if path and '.' in path:
                    # we explicitly are passing '.' to subdatasets in case of
                    # `recursive`. Therefore these datasets are going into
                    # `publish_subs`, instead of `expl_subs`:
                    sub = Dataset(opj(ds.path, subds_path))
                    publish_subs[sub.path] = dict()
                    publish_subs[sub.path]['dataset'] = sub
                    publish_subs[sub.path]['files'] = ['.']
                else:
                    # we can recursively publish only, if there actually
                    # is something
                    expl_subs.add(subds_path)

        published, skipped = [], []

        for dspath in sorted(expl_subs):
            # these datasets need to be pushed regardless of additional paths
            # pointing inside them
            # due to API, this may not happen when calling publish with paths,
            # therefore force it.
            # TODO: There might be a better solution to avoid two calls of
            # publish() on the very same Dataset instance
            ds_ = Dataset(opj(ds.path, dspath))
            try:
                # we could take local diff for the subdataset
                # but may be we could just rely on internal logic within
                # subdataset to figure out what it needs to publish.
                # But we need to pass empty string one inside as is
                pkw = {}
                if since == '':
                    pkw['since'] = since
                else:
                    # pass previous state for that submodule if known
                    pkw['since'] = subds_prev_hexsha.get(dspath, None)
                published_, skipped_ = ds_.publish(to=to, recursive=recursive, **pkw)
                published += published_
                skipped += skipped_
            except Exception as exc:
                if not skip_failing:
                    raise
                lgr.warning("Skipped %s: %s", ds.path, exc_str(exc))
                skipped += [ds_]

        for d in publish_subs:
            # recurse into subdatasets

            # TODO: need to fetch. see above
            publish_subs[d]['dataset'].repo.fetch(remote=to)

            published_, skipped_ = publish_subs[d]['dataset'].publish(
                to=to,
                path=publish_subs[d]['files'],
                recursive=recursive,
                annex_copy_opts=annex_copy_opts)
            published += published_
            skipped += skipped_

        if publish_this:
            # upstream branch needed for update (merge) and subsequent push,
            # in case there is no.
            # no tracking branch yet?
            set_upstream = track_branch is None

            # is `to` an already known remote?
            if dest_resolved not in ds.repo.get_remotes():
                # unknown remote
                raise ValueError("No sibling '%s' found." % dest_resolved)

            lgr.info("Publishing dataset {0} to sibling {1} "
                     "...".format(ds, dest_resolved))

            # we now know where to push to:
            _log_push_info(ds.repo.push(remote=dest_resolved,
                                        refspec=ds.repo.get_active_branch(),
                                        set_upstream=set_upstream))

            # push annex branch:
            if isinstance(ds.repo, AnnexRepo):
                ds.repo.fetch(remote=dest_resolved)
                ds.repo.merge_annex(dest_resolved)
                _log_push_info(ds.repo.push(remote=dest_resolved,
                                            refspec="git-annex:git-annex"))

            # we need to fetch
            # TODO
            # Note: This is about a gitpython issue as well as something about
            # annex -> might mean, that we need to do it in case we pushed an annex branch only.
            # Apparently, we can annex copy new files only, after this fetch. Figure it out!
            ds.repo.fetch(remote=dest_resolved)

            published.append(ds)

            if publish_files or annex_copy_opts:
                if not isinstance(ds.repo, AnnexRepo):
                    raise RuntimeError(
                        "Cannot publish content of something, that is not "
                        "part of an annex. ({0})".format(ds))

                lgr.info("Publishing data of dataset {0} ...".format(ds))
                published += ds.repo.copy_to(files=publish_files,
                                           remote=dest_resolved,
                                           options=annex_copy_opts)

        return published, skipped

    @staticmethod
    def result_renderer_cmdline(results, args):
        from datalad.ui import ui
        for res, res_label in zip(results, ('published', 'skipped')):
            if not res:
                if res_label == 'published':
                    ui.message("Nothing was %s" % res_label)
                continue
            msg = "{n} {obj} {res_label}:\n".format(
                obj='items were' if len(res) > 1 else 'item was',
                n=len(res),
                res_label=res_label)
            for item in res:
                if isinstance(item, Dataset):
                    msg += "Dataset: %s\n" % item.path
                else:
                    msg += "File: %s\n" % item
            ui.message(msg)

    @staticmethod
    def _get_changed_datasets(repo, all_subdatasets, to, since=None):
        if since == '' or not all_subdatasets:
            # we are instructed to publish all
            return all_subdatasets

        if since is None:  # default behavior - only updated since last update
            # so we figure out what was the last update
            # XXX here we assume one to one mapping of names from local branches
            # to the remote
            active_branch = repo.get_active_branch()
            since = '%s/%s' % (to, active_branch)

            if since not in repo.get_remote_branches():
                # we did not publish it before - so everything must go
                return all_subdatasets

        lgr.debug("Checking diff since %s for %s" % (since, all_subdatasets))
        diff = repo.repo.commit().diff(since, all_subdatasets)
        for d in diff:
            # not sure if it could even track renames of subdatasets
            # but let's "check"
            assert(d.a_path == d.b_path)
        return dict((d.b_path, d.b_blob.hexsha if d.b_blob else None) for d in diff)
