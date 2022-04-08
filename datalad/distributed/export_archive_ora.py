# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Export an archive of a local annex object store, suitable for an ORA remote"""

__docformat__ = 'restructuredtext'


import logging
import os
import os.path as op
import shutil
import subprocess
from argparse import REMAINDER

from datalad.utils import (
    ensure_list,
    rmtree,
)
from datalad.interface.base import (
    Interface,
    build_doc,
)
from datalad.interface.results import (
    get_status_dict,
)
from datalad.interface.utils import eval_results
from datalad.support.param import Parameter
from datalad.support.constraints import (
    EnsureChoice,
    EnsureNone,
    EnsureStr,
)
from datalad.support.exceptions import CapturedException
from datalad.distribution.dataset import (
    EnsureDataset,
    datasetmethod,
    require_dataset,
    resolve_path,
)
from datalad.log import log_progress

lgr = logging.getLogger('datalad.customremotes.export_archive_ora')


@build_doc
class ExportArchiveORA(Interface):
    """Export an archive of a local annex object store for the ORA remote.

    Keys in the local annex object store are reorganized in a temporary
    directory (using links to avoid storage duplication) to use the
    'hashdirlower' setup used by git-annex for bare repositories and
    the directory-type special remote. This alternative object store is
    then moved into a 7zip archive that is suitable for use in a
    ORA remote dataset store. Placing such an archive into::

      <dataset location>/archives/archive.7z

    Enables the ORA special remote to locate and retrieve all keys contained
    in the archive.
    """
    _params_ = dict(
        dataset=Parameter(
            args=("-d", "--dataset"),
            doc="""specify the dataset to process.  If
            no dataset is given, an attempt is made to identify the dataset
            based on the current working directory""",
            constraints=EnsureDataset() | EnsureNone()),
        target=Parameter(
            args=("target",),
            metavar="TARGET",
            doc="""if an existing directory, an 'archive.7z' is placed into
            it, otherwise this is the path to the target archive""",
            constraints=EnsureStr() | EnsureNone()),
        remote=Parameter(
            args=("--for",),
            dest="remote",
            metavar='LABEL',
            doc="""name of the target sibling, wanted/preferred settings
            will be used to filter the files added to the archives""",
            constraints=EnsureStr() | EnsureNone()),
        annex_wanted=Parameter(
            args=("--annex-wanted",),
            metavar="FILTERS",
            doc="""git-annex-preferred-content expression for
            git-annex find to filter files. Should start with
            'or' or 'and' when used in combination with `--for`"""),
        froms=Parameter(
            args=("--from",),
            dest="froms",
            metavar="FROM",
            nargs="+",
            doc="""one or multiple tree-ish from which to select files"""),
        opts=Parameter(
            args=("opts",),
            nargs=REMAINDER,
            metavar="...",
            doc="""list of options for 7z to replace the default '-mx0' to
            generate an uncompressed archive"""),
        missing_content=Parameter(
            args=("--missing-content",),
            doc="""By default, any discovered file with missing content will
            result in an error and the export is aborted. Setting this to
            'continue' will issue warnings instead of failing on error. The
            value 'ignore' will only inform about problem at the 'debug' log
            level. The latter two can be helpful when generating a TAR archive
            from a dataset where some file content is not available
            locally.""",
            constraints=EnsureChoice("error", "continue", "ignore")),
    )

    @staticmethod
    @datasetmethod(name='export_archive_ora')
    @eval_results
    def __call__(
            target,
            opts=None,
            *,  # opts is positional but optional in CLI
            dataset=None,
            remote=None,
            annex_wanted=None,
            froms=None,
            missing_content='error',):
        # only non-bare repos have hashdirmixed, so require one
        ds = require_dataset(
            dataset, check_installed=True, purpose='export to ORA archive')
        ds_repo = ds.repo

        annex_objs = ds_repo.dot_git / 'annex' / 'objects'

        archive = resolve_path(target, dataset)
        if archive.is_dir():
            archive = archive / 'archive.7z'
        else:
            archive.parent.mkdir(exist_ok=True, parents=True)

        froms = ensure_list(froms)

        if not opts:
            # uncompressed by default
            opts = ['-mx0']

        res_kwargs = dict(
            action="export-archive-ora",
            logger=lgr,
        )

        if not annex_objs.is_dir():
            yield get_status_dict(
                ds=ds,
                status='notneeded',
                message='no annex keys present',
                **res_kwargs,
            )
            return

        exportdir = ds_repo.dot_git / 'datalad' / 'tmp' / 'ora_archive'
        if exportdir.exists():
            yield get_status_dict(
                ds=ds,
                status='error',
                message=(
                    'export directory already exists, please remove first: %s',
                    str(exportdir)),
                **res_kwargs,
            )
            return

        def expr_to_opts(expr):
            opts = []
            expr = expr.replace('(', ' ( ').replace(')', ' ) ')
            for sub_expr in expr.split(' '):
                if len(sub_expr):
                    if sub_expr in '()':
                        opts.append(f"-{sub_expr}")
                    else:
                        opts.append(f"--{sub_expr}")
            return opts

        find_filters = []
        if remote:
            find_filters = ['-('] + expr_to_opts(ds_repo.get_preferred_content('wanted', remote)) + ['-)']
        if annex_wanted:
            find_filters.extend(expr_to_opts(annex_wanted))
        # git-annex find results need to be uniqued with set, as git-annex find
        # will return duplicates if multiple symlinks point to the same key.
        if froms:
            keypaths = set([
                annex_objs.joinpath(k) for treeish in froms for k in ds_repo.call_annex_items_([
                'find', *find_filters, f"--branch={treeish}",
                "--format=${hashdirmixed}${key}/${key}\\n"])
                ])
        else:
            keypaths = set(annex_objs.joinpath(k) for k in ds_repo.call_annex_items_([
                'find', *find_filters,
                "--format=${hashdirmixed}${key}/${key}\\n"
            ]))

        log_progress(
            lgr.info,
            'oraarchiveexport',
            'Start ORA archive export %s', ds,
            total=len(keypaths),
            label='ORA archive export',
            unit=' Keys',
        )

        if missing_content == 'continue':
            missing_file_lgr_func = lgr.warning
        elif missing_content == 'ignore':
            missing_file_lgr_func = lgr.debug

        link_fx = os.link
        for keypath in keypaths:
            key = keypath.name
            hashdir = op.join(keypath.parts[-4], keypath.parts[-3])
            log_progress(
                lgr.info,
                'oraarchiveexport',
                'Export key %s to %s', key, hashdir,
                update=1,
                increment=True)
            keydir = exportdir / hashdir / key
            keydir.mkdir(parents=True, exist_ok=True)
            try:
                link_fx(str(keypath), str(keydir / key))
            except FileNotFoundError as e:
                if missing_content == 'error':
                    raise IOError('Key %s has no content available' % keypath)
                missing_file_lgr_func(
                    'Key %s has no content available',
                    str(keypath))
            except OSError:
                lgr.warning(
                    'No hard links supported at %s, will copy files instead',
                    str(keypath))
                # no hard links supported
                # switch function after first error
                link_fx = shutil.copyfile
                link_fx(str(keypath), str(keydir / key))

        log_progress(
            lgr.info,
            'oraarchiveexport',
            'Finished RIA archive export from %s', ds
        )
        try:
            subprocess.run(
                ['7z', 'u', str(archive), '.'] + opts,
                cwd=str(exportdir),
            )
            yield get_status_dict(
                path=str(archive),
                type='file',
                status='ok',
                **res_kwargs)
        except Exception as e:
            ce = CapturedException(e)
            yield get_status_dict(
                path=str(archive),
                type='file',
                status='error',
                message=('7z failed: %s', ce),
                exception=ce,
                **res_kwargs)
            return
        finally:
            rmtree(str(exportdir))
