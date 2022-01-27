# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

__docformat__ = 'restructuredtext'

import itertools
from logging import getLogger

from datalad.consts import (
    ANNEX_TEMP_DIR,
    ANNEX_TRANSFER_DIR,
    ARCHIVES_TEMP_DIR,
    SEARCH_INDEX_DOTGITDIR,
)
from datalad.distribution.dataset import (
    EnsureDataset,
    datasetmethod,
    require_dataset,
)
from datalad.interface.base import (
    Interface,
    build_doc,
)
from datalad.interface.common_opts import (
    recursion_flag,
    recursion_limit,
)
from datalad.interface.results import get_status_dict
from datalad.interface.utils import eval_results
from datalad.support.constraints import EnsureNone
from datalad.support.param import Parameter
from datalad.utils import (
    Path,
    rmtree,
)

lgr = getLogger('datalad.local.clean')


@build_doc
class Clean(Interface):
    """Clean up after DataLad (possible temporary files etc.)

    Removes temporary files and directories left behind by DataLad and
    git-annex in a dataset.

    """

    result_renderer = 'tailored'

    _examples_ = [
        dict(text="Clean all known temporary locations of a dataset",
             code_py="clean()",
             code_cmd="datalad clean"),
        dict(text="Report on all existing temporary locations of a dataset",
             code_py="clean(dry_run=True)",
             code_cmd="datalad clean --dry-run"),
        dict(text="Clean all known temporary locations of a dataset and all "
                  "its subdatasets",
             code_py="clean(recursive=True)",
             code_cmd="datalad clean -r"),
        dict(text="Clean only the archive extraction caches of a dataset and "
                  "all its subdatasets",
             code_py="clean(what='cached-archives', recursive=True)",
             code_cmd="datalad clean --what cached-archives -r"),
        dict(text="Report on existing annex transfer files of a dataset and "
                  "all its subdatasets",
             code_py="clean(what='annex-transfer', recursive=True, "
                     "dry_run=True)",
             code_cmd="datalad clean --what annex-transfer -r --dry-run"),
    ]

    _params_ = dict(
        dataset=Parameter(
            args=("-d", "--dataset"),
            doc="""specify the dataset to perform the clean operation on.  If
                no dataset is given, an attempt is made to identify the dataset
                in current working directory""",
            constraints=EnsureDataset() | EnsureNone()),
        dry_run=Parameter(
            args=("--dry-run",),
            doc="""Report on cleanable locations - not actually cleaning up
            anything.""",
            action="store_true", ),
        # TODO: Python only???
        what=Parameter(
            args=("--what",),
            dest='what',
            choices=('cached-archives', 'annex-tmp', 'annex-transfer',
                     'search-index'),
            nargs="*",
            doc="""What to clean. If none specified -- all known
            targets are considered."""),
        recursive=recursion_flag,
        recursion_limit=recursion_limit,
    )

    @staticmethod
    @datasetmethod(name='clean')
    @eval_results
    def __call__(*,
                 dataset=None, what=None, dry_run=False,
                 recursive=False, recursion_limit=None):

        ds = require_dataset(dataset,
                             purpose="report on cleanable locations"
                             if dry_run else "clean dataset")
        res_kwargs = dict(action='clean [dry-run]' if dry_run else 'clean',
                          logger=lgr, refds=ds.path)
        for wds in itertools.chain([ds], ds.subdatasets(
                state='present',
                recursive=recursive,
                recursion_limit=recursion_limit,
                return_type='generator',
                result_renderer='disabled',
                result_xfm='datasets') if recursive else []):
            d = wds.pathobj
            gitdir = wds.repo.dot_git
            DIRS_PLURAL = ("directory", "directories")
            FILES_PLURAL = ("file", "files")
            discover_or_remove = "Discovered" if dry_run else "Removed"

            for dirpath, flag, msg, sing_pl in [
                (Path(ARCHIVES_TEMP_DIR), "cached-archives",
                 "temporary archive", DIRS_PLURAL),
                (Path(ANNEX_TEMP_DIR), "annex-tmp",
                 "temporary annex", FILES_PLURAL),
                (Path(ANNEX_TRANSFER_DIR), "annex-transfer",
                 "annex temporary transfer", DIRS_PLURAL),
                (gitdir / Path(SEARCH_INDEX_DOTGITDIR), 'search-index',
                 "metadata search index", FILES_PLURAL),
            ]:
                topdir = wds.pathobj / dirpath
                lgr.debug("Considering to clean %s:%s", d, dirpath)
                if not ((what is None) or (flag in what)):
                    yield get_status_dict(
                        path=str(topdir), status='notneeded', type='directory',
                        **res_kwargs)
                    continue

                paths = [p for p in topdir.glob('*')]
                if not paths:
                    if not topdir.exists():
                        yield get_status_dict(
                            path=str(topdir), status='notneeded',
                            type='directory', **res_kwargs)
                        continue
                    else:
                        # we empty topdir only
                        message = ("%s empty %s directory",
                                   discover_or_remove,
                                   msg)
                else:
                    pl = len(paths) > 1
                    message = ("%s %d %s %s: %s",
                               discover_or_remove,
                               len(paths), msg, sing_pl[int(pl)],
                               ", ".join(sorted([str(p.relative_to(topdir))
                                                 for p in paths if p != topdir]
                                                )
                                         )
                               )

                if not dry_run:
                    rmtree(str(topdir))

                yield get_status_dict(path=str(topdir),
                                      status='ok',
                                      type='directory',
                                      message=message,
                                      **res_kwargs)

    @staticmethod
    def custom_result_renderer(res, **kwargs):  # pragma: more cover
        # Don't render things like 'status' for clean-info messages -
        # seems rather meaningless.

        from os import getcwd

        import datalad.support.ansi_colors as ac
        from datalad.interface.utils import generic_result_renderer
        from datalad.utils import Path

        if res['action'] == 'clean':
            # default renderer is just fine
            return generic_result_renderer(res)
        elif res['action'] != 'clean [dry-run]':
            # Result didn't come from within `clean`.
            # Should be handled elsewhere.
            return

        assert res['action'] == 'clean [dry-run]'

        if res.get('status', None) == 'ok':
            from datalad.ui import ui

            # when to render relative paths:
            #  1) if a dataset arg was given
            #  2) if CWD is the refds

            refds = res.get('refds', None)
            refds = refds if kwargs.get('dataset', None) is not None \
                             or refds == getcwd() else None
            path = res['path'] if refds is None \
                else str(Path(res['path']).relative_to(refds))

            ui.message(u"{path}: {message}".format(
                path=ac.color_word(path, ac.BOLD),
                message=(res['message'][0] % res['message'][1:]
                         if isinstance(res['message'], tuple)
                         else res['message'])
                if res.get('message', None) else ''
            )
            )

        else:
            # Any other status than 'ok' is reported the default way.
            return generic_result_renderer(res)

    @staticmethod
    def custom_result_summary_renderer(results):
        # Since 'notneeded' results aren't rendered by default, give
        # a nothing-to-clean-message if all results were "notneeded",
        # to not remain entirely silent.

        if all(r['status'] == 'notneeded' for r in results):
            from datalad.ui import ui
            ui.message("nothing to clean, no temporary locations present.")
