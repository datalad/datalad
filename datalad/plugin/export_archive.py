# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""export a dataset as a compressed TAR/ZIP archive"""

__docformat__ = 'restructuredtext'


# PLUGIN API
def dlplugin(dataset, filename=None, archivetype='tar', compression='gz',
             missing_content='error'):
    """Export the content of a dataset as a TAR/ZIP archive.

    Parameters
    ----------
    filename : str, optional
      File name of the generated TAR archive. If no file name is given
      the archive will be generated in the current directory and will
      be named: datalad_<dataset_uuid>.(tar.*|zip).
    archivetype : {'tar', 'zip'}
      Type of archive to generate.
    compression : {'', 'gz', 'bz2')
      Compression method to use. 'bz2' is not supported for ZIP archives.
    missing_content : {'error', 'continue', 'ignore'}, optional
      By default, any discovered file with missing content will result in
      an error and the plugin is aborted. Setting this to 'continue' will
      issue warnings instead of failing on error. The value 'ignore' will
      only inform about problem at the 'debug' log level. The latter two
      can be helpful when generating a TAR archive from a dataset where
      some file content is not available locally.

    """
    import os
    import tarfile
    import zipfile
    from mock import patch
    from os.path import join as opj, dirname, normpath, isabs
    from datalad.utils import file_basename
    from datalad.support.annexrepo import AnnexRepo
    from datalad.dochelpers import exc_str

    import logging
    lgr = logging.getLogger('datalad.plugin.export_archive')

    repo = dataset.repo
    committed_date = repo.get_committed_date()

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

    if filename is None:
        filename = "datalad_{}".format(dataset.id)
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
