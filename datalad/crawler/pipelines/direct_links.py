# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""A pipeline for crawling direct links (to archives)"""

# Import necessary nodes
from ..pipelines.simple_with_archives import pipeline as swa_pipeline
from ...consts import ARCHIVES_SPECIAL_REMOTE
from ..nodes.misc import BuildRIs
from ..nodes.annex import Annexificator
from logging import getLogger
lgr = getLogger("datalad.crawler.pipelines.direct_links")


def pipeline(
        paths=None,
        leading_dirs_depth=1,
        tarballs=True,
        use_current_dir=False,
        rename=None,   # how to? => target file
        backend='MD5E',
        add_archive_leading_dir=False,
        annex=None,
        incoming_pipeline=None):
    lgr.info("Creating a pipeline for plain archive import with paths %s" % paths)

    if annex is None:
        # if no annex to use was provided -- let's just make one
        special_remotes = []
        if tarballs:
            special_remotes.append(ARCHIVES_SPECIAL_REMOTE)
        # if datalad_downloader:
        #     special_remotes.append(DATALAD_SPECIAL_REMOTE)
        annex = Annexificator(
            create=False,  # must be already initialized etc
            backend=backend,
            statusdb='json',
            special_remotes=special_remotes,
            largefiles="exclude=README* and exclude=LICENSE*",
            allow_dirty=True
        )

    pipe = incoming_pipeline if incoming_pipeline else []
    pipe.append(BuildRIs(paths))
    #pipe.append(debug)
    pipe.append(annex)  #? => wrong branch?!
    #pipe.append(debug)

    return swa_pipeline(url=None,
                        a_href_match_=None,
                        tarballs=tarballs,
                        datalad_downloader=False,
                        use_current_dir=use_current_dir,
                        leading_dirs_depth=leading_dirs_depth,
                        rename=rename,
                        backend=backend,
                        add_archive_leading_dir=add_archive_leading_dir,
                        annex=annex,
                        incoming_pipeline=pipe)


