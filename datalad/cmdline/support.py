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

__docformat__ = "restructuredtext"

from datalad.utils import swallow_outputs
from datalad.api import wtf
import sys
import os

from logging import getLogger

lgr = getLogger("datalad.cmdline")

os.environ["MESSAGELEVEL"] = "QUIET"
os.putenv("MESSAGELEVEL", "QUIET")

repo = "datalad/datalad-helpme"
default_title = "Test issue opened manually by helpme"


def submit_helpme(detail=None, title=None):
    """Submit a request to the datalad-helpme repository at
       https://github.com/datalad/datalad-helpme. If helpme isn't installed,
       we skip this step. The basic submission includes the entire grab from
       wtf (capturing system and library information) and an optional message.
    """
    title = title or default_title

    # If the user requests to disable, don't submit
    if os.environ.get("DATALAD_HELPME_DISABLE") is not None:
        return

    # Default sections to include for a reasonably sized message
    sections = [
        "datalad",
        "python",
        "system",
        "environment",
        "configuration",
        "location",
        "extensions",
        "metadata_extractors",
        "dependencies",
        "dataset",
    ]

    try:
        from helpme.main import get_helper

        helper = get_helper(name="github")

        with swallow_outputs() as cmo:
            wtf(decor="html_details", sections=sections)
            body = """
**What were you trying to do?**

**Is there anything else you want to tell us**

<!-- Have you had any success using DataLad before? (to assess your expertise/prior luck.  We would welcome your testimonial additions to https://github.com/datalad/datalad/wiki/Testimonials as well)-->

----------------------------------------------------------------
### Metadata
**Error Message :name_badge:**
%s

**WTF Output** :open_file_folder:
%s""" % (
                detail or "",
                cmo.out,
            )

        # Submit the issue
        issue = helper.run_headless(repo=repo, body=body, title=title)

    except:
        pass
