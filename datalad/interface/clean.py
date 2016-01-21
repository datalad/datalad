# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

__docformat__ = 'restructuredtext'

from six.moves.urllib.request import urlopen, Request
from six.moves.urllib.error import HTTPError

from os.path import join as opj
from glob import glob
from .base import Interface
from ..ui import ui
from ..utils import rmtree
from ..support.param import Parameter
from ..support.constraints import EnsureStr, EnsureNone
from ..support.annexrepo import AnnexRepo
from ..cmdline.helpers import get_repo_instance
from ..consts import ARCHIVES_TEMP_DIR

from logging import getLogger
lgr = getLogger('datalad.api.clean')


class Clean(Interface):
    """Clean up after DataLad (e.g. extracted temporary archives etc)

    Examples:

      $ datalad clean
    """

    _params_ = dict(
        # TODO:  --info  -- which performs dry run just summarizing what is to be cleaned up
        # TODO: Python only???
        annex=Parameter(
            doc="""Annex instance to use""" #,
            #constraints=EnsureStr() | EnsureNone()
        ),
    )

    def __call__(self, annex=None):
        if annex is None:
            annex = get_repo_instance(class_=AnnexRepo)
        archive_temp_topdir = opj(annex.path, ARCHIVES_TEMP_DIR)
        temp_archives_dirs = glob(opj(annex.path, ARCHIVES_TEMP_DIR, '*'))
        if temp_archives_dirs:
            ui.message("Removing %d temporary archives directories: %s"
                       % (len(temp_archives_dirs), ", ".join(temp_archives_dirs)))
            rmtree(archive_temp_topdir)