# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""export a dataset as a compressed TAR/ZIP archive"""

__docformat__ = 'restructuredtext'

from datalad.interface.base import Interface
from datalad.interface.base import build_doc
from datalad.support import path


@build_doc
class ExportArchive(Interface):
    """Export the content of a dataset as a TAR/ZIP archive.
    """
    from datalad.support.param import Parameter
    from datalad.distribution.dataset import datasetmethod
    from datalad.interface.utils import eval_results
    from datalad.distribution.dataset import EnsureDataset
    from datalad.support.constraints import (
        EnsureChoice,
        EnsureNone,
        EnsureStr,
    )

    _params_ = dict(
        dataset=Parameter(
            args=("-d", "--dataset"),
            doc=""""specify the dataset to export. If no dataset is given, an
            attempt is made to identify the dataset based on the current
            working directory.""",
            constraints=EnsureDataset() | EnsureNone()),
        filename=Parameter(
            args=("filename",),
            metavar="PATH",
            nargs='?',
            doc="""File name of the generated TAR archive. If no file name is
            given the archive will be generated in the current directory and
            will be named: datalad_<dataset_uuid>.(tar.*|zip). To generate that
            file in a different directory, provide an existing directory as the
            file name.""",
            constraints=EnsureStr() | EnsureNone()),
        archivetype=Parameter(
            args=("-t", "--archivetype"),
            doc="""Type of archive to generate.""",
            constraints=EnsureChoice("tar", "zip")),
        compression=Parameter(
            args=("-c", "--compression"),
            doc="""Compression method to use.  'bz2' is not supported for ZIP
            archives.  No compression is used when an empty string is
            given.""",
            constraints=EnsureChoice("gz", "bz2", "")),
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
    @datasetmethod(name='export_archive')
    @eval_results
    def __call__(filename=None,
                 *,
                 dataset=None,
                 archivetype='tar',
                 compression='gz',
                 missing_content='error'):
        import os
        import tarfile
        import zipfile
        from unittest.mock import patch
        from os.path import join as opj, dirname, normpath, isabs
        import os.path as op

        from datalad.distribution.dataset import require_dataset
        from datalad.utils import file_basename
        from datalad.support.annexrepo import AnnexRepo

        import logging
        lgr = logging.getLogger('datalad.local.export_archive')

        dataset = require_dataset(dataset, check_installed=True,
                                  purpose='export archive')

        repo = dataset.repo
        committed_date = repo.get_commit_date()

        # could be used later on to filter files by some criterion
        def _filter_tarinfo(ti):
            # Reset the date to match the one of the last commit, not from the
            # filesystem since git doesn't track those at all
            # TODO: use the date of the last commit when any particular
            # file was changed -- would be the most kosher yoh thinks to the
            # degree of our abilities
            ti.mtime = committed_date
            return ti
        tar_args = dict(recursive=False, filter=_filter_tarinfo)

        file_extension = '.{}{}'.format(
            archivetype,
            '{}{}'.format(
                '.' if compression else '',
                compression) if archivetype == 'tar' else '')

        default_filename = "datalad_{.id}".format(dataset)
        if filename is None:
            filename = default_filename  # in current directory
        elif path.exists(filename) and path.isdir(filename):
            filename = path.join(filename, default_filename) # under given directory
        if not filename.endswith(file_extension):
            filename += file_extension

        root = dataset.path
        # use dir inside matching the output filename
        # TODO: could be an option to the export plugin allowing empty value
        # for no leading dir
        leading_dir = file_basename(filename)

        # workaround for inability to pass down the time stamp
        with patch('time.time', return_value=committed_date), \
                tarfile.open(filename, "w:{}".format(compression)) \
                if archivetype == 'tar' \
                else zipfile.ZipFile(
                    filename, 'w',
                    zipfile.ZIP_STORED if not compression else zipfile.ZIP_DEFLATED) \
                as archive:
            add_method = archive.add if archivetype == 'tar' else archive.write
            repo_files = sorted(repo.get_indexed_files())
            if isinstance(repo, AnnexRepo):
                annexed = repo.is_under_annex(
                    repo_files, allow_quick=True, batch=True)
                # remember: returns False for files in Git!
                has_content = repo.file_has_content(
                    repo_files, allow_quick=True, batch=True)
            else:
                annexed = [False] * len(repo_files)
                has_content = [True] * len(repo_files)
            for i, rpath in enumerate(repo_files):
                fpath = opj(root, rpath)
                if annexed[i]:
                    if not has_content[i]:
                        if missing_content in ('ignore', 'continue'):
                            (lgr.warning if missing_content == 'continue' else lgr.debug)(
                                'File %s has no content available, skipped', fpath)
                            continue
                        else:
                            raise IOError('File %s has no content available' % fpath)

                    # resolve to possible link target
                    if op.islink(fpath):
                        link_target = os.readlink(fpath)
                        if not isabs(link_target):
                            link_target = normpath(opj(dirname(fpath), link_target))
                        fpath = link_target
                # name in the archive
                aname = normpath(opj(leading_dir, rpath))
                add_method(
                    fpath,
                    arcname=aname,
                    **(tar_args if archivetype == 'tar' else {}))

        if not isabs(filename):
            filename = opj(os.getcwd(), filename)

        yield dict(
            status='ok',
            path=filename,
            type='file',
            action='export_archive',
            logger=lgr)
