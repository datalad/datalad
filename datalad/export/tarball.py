# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""

"""

__docformat__ = 'restructuredtext'

import logging
import tarfile
import os

from mock import patch
from os.path import join as opj, dirname, normpath, isabs
from datalad.support.annexrepo import AnnexRepo
from datalad.utils import file_basename

lgr = logging.getLogger('datalad.export.tarball')


# PLUGIN API
def _datalad_export_plugin_call(dataset, output, argv=None):
    if argv:
        lgr.warn("tarball exporter ignores any additional options '{}'".format(
            argv))

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

    if output is None:
        output = "datalad_{}.tar.gz".format(dataset.id)
    else:
        if not output.endswith('.tar.gz'):
            output += '.tar.gz'

    root = dataset.path
    # use dir inside matching the output filename
    # TODO: could be an option to the export plugin allowing empty value
    # for no leading dir
    leading_dir = file_basename(output)

    # workaround for inability to pass down the time stamp
    with patch('time.time', return_value=committed_date), \
            tarfile.open(output, "w:gz") as tar:
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
            tar.add(
                fpath,
                arcname=aname,
                recursive=False,
                filter=_filter_tarinfo)

    # I think it might better return "final" filename where stuff was saved
    return output


# PLUGIN API
def _datalad_get_cmdline_help():
    return 'Just call it, and it will produce a tarball.'
