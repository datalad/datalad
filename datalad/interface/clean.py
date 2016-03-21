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
from ..utils import rmtree, getpwd
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

    @staticmethod
    def __call__(annex=None):
        if annex is None:
            annex = get_repo_instance(class_=AnnexRepo)
        topdir = opj(annex.path, ARCHIVES_TEMP_DIR)
        temp_archives_dirs = glob(opj(annex.path, ARCHIVES_TEMP_DIR, '*'))
        if temp_archives_dirs:
            pl = len(temp_archives_dirs) > 1
            pl1, pl2 = ('s', 'ies') if pl else ('', 'y')
            
            pwd = getpwd()
            # relative version if possible
            rtopdir = topdir[len(pwd)+1:] if topdir.startswith(pwd) else topdir
            ui.message("Removing %d temporary archive director%s under %s: %s"
                       % (len(temp_archives_dirs), pl2,
                          rtopdir,
                          ", ".join(sorted([x[len(topdir)+1:] for x in temp_archives_dirs]))))
            rmtree(topdir)
