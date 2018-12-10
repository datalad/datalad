# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""For now just a proxy to git annex unlock

"""

__docformat__ = 'restructuredtext'

import logging

from os.path import join as opj

from datalad.support.constraints import EnsureStr
from datalad.support.constraints import EnsureNone
from datalad.support.exceptions import InsufficientArgumentsError
from datalad.support.annexrepo import AnnexRepo
from datalad.support.param import Parameter
from datalad.distribution.dataset import Dataset
from datalad.distribution.dataset import EnsureDataset
from datalad.distribution.dataset import datasetmethod
from datalad.interface.annotate_paths import AnnotatePaths
from datalad.interface.annotate_paths import annotated2content_by_ds
from datalad.interface.results import get_status_dict
from datalad.interface.utils import eval_results
from datalad.interface.base import build_doc
from datalad.interface.common_opts import recursion_flag
from datalad.interface.common_opts import recursion_limit

from .base import Interface

lgr = logging.getLogger('datalad.interface.unlock')


@build_doc
class Unlock(Interface):
    """Unlock file(s) of a dataset

    Unlock files of a dataset in order to be able to edit the actual content
    """

    _params_ = dict(
        path=Parameter(
            args=("path",),
            doc="""file(s) to unlock""",
            nargs="*",
            constraints=EnsureStr() | EnsureNone()),
        dataset=Parameter(
            args=("-d", "--dataset"),
            doc=""""specify the dataset to unlock files in. If
            no dataset is given, an attempt is made to identify the dataset
            based on the current working directory. If the latter fails, an
            attempt is made to identify the dataset based on `path` """,
            constraints=EnsureDataset() | EnsureNone()),
        recursive=recursion_flag,
        recursion_limit=recursion_limit,
    )

    @staticmethod
    @datasetmethod(name='unlock')
    @eval_results
    def __call__(
            path=None,
            dataset=None,
            recursive=False,
            recursion_limit=None):

        if path is None and dataset is None:
            raise InsufficientArgumentsError(
                "insufficient arguments for unlocking: needs at least "
                "a dataset or a path to unlock.")

        refds_path = Interface.get_refds_path(dataset)
        res_kwargs = dict(action='unlock', logger=lgr, refds=refds_path)

        to_process = []
        for ap in AnnotatePaths.__call__(
                dataset=refds_path,
                path=path,
                recursive=recursive,
                recursion_limit=recursion_limit,
                action='unlock',
                unavailable_path_status='impossible',
                unavailable_path_msg="path does not exist",
                nondataset_path_status='impossible',
                modified=None,
                return_type='generator',
                on_failure='ignore'):
            if ap.get('status', None):
                # this is done
                yield ap
                continue
            if ap.get('type', 'dataset') == 'dataset':
                # this is a dataset
                ap['process_content'] = True
            to_process.append(ap)

        content_by_ds, ds_props, completed, nondataset_paths = \
            annotated2content_by_ds(
                to_process,
                refds_path=refds_path)
        assert(not completed)

        for ds_path in sorted(content_by_ds.keys()):
            ds = Dataset(ds_path)
            content = content_by_ds[ds_path]

            # no annex, no unlock:
            if not isinstance(ds.repo, AnnexRepo):
                for ap in content:
                    ap['status'] = 'notneeded'
                    ap['message'] = "not annex'ed, nothing to unlock"
                    ap.update(res_kwargs)
                    yield ap
                continue

            # direct mode, no unlock:
            elif ds.repo.is_direct_mode():
                for ap in content:
                    ap['status'] = 'notneeded'
                    ap['message'] = "direct mode, nothing to unlock"
                    ap.update(res_kwargs)
                    yield ap
                continue

            # only files in annex with their content present:
            files = [ap['path'] for ap in content]
            to_unlock = []
            for ap, under_annex, has_content in \
                zip(content,
                    ds.repo.is_under_annex(files),
                    ds.repo.file_has_content(files)):

                # TODO: what about directories? Make sure, there is no
                # situation like no file beneath with content or everything in
                # git, that leads to a CommandError
                # For now pass to annex:
                from os.path import isdir
                if isdir(ap['path']):
                    to_unlock.append(ap)
                    continue

                # Note, that `file_has_content` is (planned to report) True on
                # files in git. Therefore order matters: First check for annex!
                if under_annex:
                    if has_content:
                        to_unlock.append(ap)
                    # no content, no unlock:
                    else:
                        ap['status'] = 'impossible'
                        ap['message'] = "no content present, can't unlock"
                        ap.update(res_kwargs)
                        yield ap
                # file in git, no unlock:
                else:
                    ap['status'] = 'notneeded'
                    ap['message'] = "not controlled by annex, nothing to unlock"
                    ap.update(res_kwargs)
                    yield ap

            # don't call annex-unlock with no path, if this is this case because
            # nothing survived the filtering above
            if content and not to_unlock:
                continue

            for r in ds.repo.unlock([ap['path'] for ap in to_unlock]):
                yield get_status_dict(
                    path=opj(ds.path, r),
                    status='ok',
                    type='file',
                    **res_kwargs)
