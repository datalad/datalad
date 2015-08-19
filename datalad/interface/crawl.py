# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Interface for crawling a webpage and push extracted data into a handle"""

__docformat__ = 'restructuredtext'

from .base import Interface
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureStr, EnsureChoice

class Crawl(Interface):
    """Crawl a webpage and push extracted data into a handle

    Examples:

    $ datalad crawl cfgs/openfmri.cfg
    """
    _params_ = dict(
        configs=Parameter(
            metavar='file',
            nargs='+',
            constraints=EnsureStr(),
            doc="""Configuration file(s) defining the structure of the
            'project'"""),
        existing=Parameter(
            choices=('check', 'skip'),
            doc="""How to deal with files already known. 'skip' would
            entirely skip file without checking if it was modified or
            not. 'check' would proceed normally updating the file(s) if
            changed""",
            constraints=EnsureChoice('check', 'skip')),
        dry_run=Parameter(
            args=("-n", "--dry-run"),
            action="store_true",
            doc="""Flag if git-annex is to be invoked. If not, commands are
            only printed to the stdout"""),
        cache=Parameter(
            action="store_true",
            doc="Flag whether to cache fetching of pages and parsing out urls")
    )

    def __call__(configs, existing='check', dry_run=False, cache=False):
        from datalad.api import DoubleAnnexRepo, load_config

        cfg = load_config(configs)

        drepo = DoubleAnnexRepo(cfg)
        drepo.page2annex(existing=existing, dry_run=dry_run,
                         cache=cache)
