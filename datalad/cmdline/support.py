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

import os
import sys

from logging import getLogger

lgr = getLogger("datalad.cmdline")

# Set defaults for repository and title for issue
default_repo = "datalad/datalad-helpme"
default_title = "Test issue opened manually by helpme"


def submit_helpme(title=None, traceback="", detail="", identifier=None, repo=None):
    """Submit a request to the datalad-helpme repository at
       https://github.com/datalad/datalad-helpme. If helpme isn't installed,
       we skip this step. The basic submission includes the entire grab from
       wtf (capturing system and library information) and an optional message.

       Parameters
       ----------
       title : str
         the title for the GitHub issue
       detail : str
         any extra string content to include with the message.
       traceback : str
         the full traceback
       identifier : str 
         the identifier string (will use traceback if not defined)
       repo : str
         GitHub repo (<username>/<repo>) to submit to.
    """
    title = title or default_title
    repo = repo or default_repo

    # If no identifier defined, use traceback
    if identifier is None:
        identifier = traceback

    # If the user requests to disable, or in testing environment don't submit
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

    # Disable helpme additional verbosity
    os.environ["HELPME_MESSAGELEVEL"] = "QUIET"
    os.putenv("HELPME_MESSAGELEVEL", "QUIET")

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
**Command :star:**
```bash
%s
```
**Error Message :name_badge:**
```python
%s
```
**WTF Output** :open_file_folder:
%s""" % (detail, traceback, cmo.out)

        # Submit the issue
        issue = helper.run_headless(
            repo=repo, body=body, title=title, identifier=identifier
        )

    except ImportError:
        lgr.debug("helpme is not installed to report issues: pip install helpme[github]")
        pass
