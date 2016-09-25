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
from os.path import join as opj, dirname, normpath, isabs
from datalad.support.annexrepo import AnnexRepo

lgr = logging.getLogger('datalad.export.tarball')


# PLUGIN API
def _datalad_export_plugin_call(dataset, output, argv=None):
    if argv:
        lgr.warn("tarball exporter ignores any additional options '{}'".format(
            argv))

    # could be used later on to filter files by some criterion
    def _filter_tarinfo(ti):
        return ti

    if output is None:
        output = "datalad_{}.tar.gz".format(dataset.id)
    else:
        if not output.endswith('.tar.gz'):
            output += '.tar.gz'

    root = dataset.path

    with tarfile.open(output, "w:gz") as tar:
        repo_files = sorted(dataset.repo.get_indexed_files())
        if isinstance(dataset.repo, AnnexRepo):
            annexed = dataset.repo.is_under_annex(
                repo_files, allow_quick=True, batch=True)
        else:
            annexed = [False] * len(repo_file)
        for i, rpath in enumerate(repo_files):
            fpath = opj(root, rpath)
            if annexed[i]:
                # resolve to possible link target
                link_target = os.readlink(fpath)
                if not isabs(link_target):
                    link_target = normpath(opj(dirname(fpath), link_target))
                fpath = link_target
            # name in the tarball
            aname = normpath(opj(dataset.id, rpath))
            tar.add(
                fpath,
                arcname=aname,
                recursive=False,
                filter=_filter_tarinfo)


# PLUGIN API
def _datalad_get_cmdline_help():
    return 'Just call it, and it will produce a tarball.'
