# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

__docformat__ = 'restructuredtext'


from os.path import join as opj
from glob import glob
import itertools
from .base import Interface
from ..utils import rmtree
from ..support.param import Parameter
from ..consts import (
    ARCHIVES_TEMP_DIR,
    ANNEX_TEMP_DIR,
    ANNEX_TRANSFER_DIR,
    SEARCH_INDEX_DOTGITDIR,
)

from datalad.support.gitrepo import GitRepo
from datalad.support.constraints import (
    EnsureNone,
)
from datalad.distribution.dataset import (
    EnsureDataset,
    require_dataset,
    datasetmethod,
)
from datalad.interface.common_opts import (
    recursion_flag,
    recursion_limit,
)
from datalad.interface.results import get_status_dict
from datalad.interface.utils import eval_results
from datalad.interface.base import build_doc
from logging import getLogger
lgr = getLogger('datalad.api.clean')

# needed API commands
import datalad.distribution.subdatasets


@build_doc
class Clean(Interface):
    """Clean up after DataLad (possible temporary files etc.)

    Removes extracted temporary archives, etc.

    Examples:

      $ datalad clean
    """

    result_renderer = 'tailored'

    _params_ = dict(
        dataset=Parameter(
            args=("-d", "--dataset"),
            doc="""specify the dataset to perform the clean operation on.  If
                no dataset is given, an attempt is made to identify the dataset
                in current working directory""",
            constraints=EnsureDataset() | EnsureNone()),
        dry_run = Parameter(
            args=("--dry-run",),
            doc="""Report on cleanable locations - not actually cleaning up
            anything.""",
            action="store_true",),
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
    def __call__(dataset=None, what=None, dry_run=False,
                 recursive=False, recursion_limit=None):

        ds = require_dataset(dataset,
                             purpose="report on cleanable locations"
                             if dry_run else "clean dataset")
        res_kwargs = dict(action='clean [dry-run]' if dry_run else 'clean',
                          logger=lgr, refds=ds.path)
        for wds in itertools.chain([ds], ds.subdatasets(
                fulfilled=True,
                recursive=recursive,
                recursion_limit=recursion_limit,
                return_type='generator',
                result_renderer='disabled',
                result_xfm='datasets') if recursive else []):
            d = wds.path
            gitdir = GitRepo.get_git_dir(d)
            DIRS_PLURAL = ("directory", "directories")
            FILES_PLURAL = ("file", "files")
            for dirpath, flag, msg, sing_pl in [
                (ARCHIVES_TEMP_DIR, "cached-archives",
                 "temporary archive", DIRS_PLURAL),
                (ANNEX_TEMP_DIR, "annex-tmp",
                 "temporary annex", FILES_PLURAL),
                (ANNEX_TRANSFER_DIR, "annex-transfer",
                 "annex temporary transfer", DIRS_PLURAL),
                (opj(gitdir, SEARCH_INDEX_DOTGITDIR), 'search-index',
                 "metadata search index", FILES_PLURAL),
            ]:
                topdir = opj(d, dirpath)
                lgr.debug("Considering to clean %s:%s", d, dirpath)
                if not ((what is None) or (flag in what)):
                    yield get_status_dict(
                        path=topdir, status='notneeded', type='directory', **res_kwargs)
                    continue
                paths = glob(opj(topdir, '*'))
                if not paths:
                    yield get_status_dict(
                        path=topdir, status='notneeded', type='directory', **res_kwargs)
                    continue
                pl = len(paths) > 1
                message = ("%s %d %s %s: %s",
                           "Discovered" if dry_run else "Removed",
                           len(paths), msg, sing_pl[int(pl)],
                           ", ".join(sorted([x[len(topdir) + 1:] for x in paths])))

                if not dry_run:
                    rmtree(topdir)

                yield get_status_dict(path=topdir,
                                      status='ok',
                                      type='directory',
                                      message=message,
                                      **res_kwargs)

    @staticmethod
    def custom_result_renderer(res, **kwargs):  # pragma: more cover
        # Don't render things like 'status' for clean-info messages -
        # seems rather meaningless.

        from datalad.interface.utils import default_result_renderer
        import datalad.support.ansi_colors as ac
        from datalad.utils import Path
        from os import getcwd

        if res['action'] == 'clean':
            # default renderer is just fine
            return default_result_renderer(res)
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
            return default_result_renderer(res)
