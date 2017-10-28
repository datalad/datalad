# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""export a dataset as a TAR archive"""

__docformat__ = 'restructuredtext'


# PLUGIN API
def dlplugin(dataset, filename=None, on_failure='error'):
    """Export the content of a dataset as a TAR archive.

    Parameters
    ----------
    filename : str, optional
      File name of the generated TAR archive. If no file name is given
      the archive will be generated in the current directory and will
      be named: datalad_<dataset_uuid>.tar.gz.
    on_failure : {'error', 'continue', 'ignore'}, optional
      By default, any issue accessing a file in the dataset while adding
      it to the TAR archive will result in an error and the plugin is
      aborted. Setting this to 'continue' will issue warnings instead
      of failing on error. The value 'ignore' will only inform about
      problem at the 'debug' log level. The latter two can be helpful
      when generating a TAR archive from a dataset where some file content
      is not available locally.

    """
    import os
    import tarfile
    from mock import patch
    from os.path import join as opj, dirname, normpath, isabs
    from datalad.utils import file_basename
    from datalad.support.annexrepo import AnnexRepo
    from datalad.dochelpers import exc_str

    import logging
    lgr = logging.getLogger('datalad.plugin.tarball')

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

    if filename is None:
        filename = "datalad_{}.tar.gz".format(dataset.id)
    else:
        if not filename.endswith('.tar.gz'):
            filename += '.tar.gz'

    root = dataset.path
    # use dir inside matching the output filename
    # TODO: could be an option to the export plugin allowing empty value
    # for no leading dir
    leading_dir = file_basename(filename)

    # workaround for inability to pass down the time stamp
    with patch('time.time', return_value=committed_date), \
            tarfile.open(filename, "w:gz") as tar:
        repo_files = sorted(repo.get_indexed_files())
        if isinstance(repo, AnnexRepo):
            annexed = repo.is_under_annex(
                repo_files, allow_quick=True, batch=True)
        else:
            annexed = [False] * len(repo_files)
        for i, rpath in enumerate(repo_files):
            fpath = opj(root, rpath)
            if annexed[i]:
                # resolve to possible link target
                link_target = os.readlink(fpath)
                if not isabs(link_target):
                    link_target = normpath(opj(dirname(fpath), link_target))
                fpath = link_target
            # name in the tarball
            aname = normpath(opj(leading_dir, rpath))
            try:
                tar.add(
                    fpath,
                    arcname=aname,
                    recursive=False,
                    filter=_filter_tarinfo)
            except OSError as e:
                if on_failure in('ignore', 'continue'):
                    (lgr.warning if on_failure == 'continue' else lgr.debug)(
                        'Skipped %s: %s',
                        fpath, exc_str(e))

    if not isabs(filename):
        filename = opj(os.getcwd(), filename)

    yield dict(
        status='ok',
        path=filename,
        type='file',
        action='export_tarball',
        logger=lgr)
