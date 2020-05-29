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

import hashlib
import os
import re
import sys
import traceback

from logging import getLogger

lgr = getLogger("datalad.cmdline")

# Set defaults for repository and title for issue
default_repo = "datalad/datalad-helpme"
default_title = "Test issue opened manually by helpme"


def generate_identifier_hash(itemlist):
    """generate a unique identifier (hash) from a list of strings

       Parameters
       ----------
       itemlist: list (str)
         list of strings to add to the hash
    """
    if not isinstance(itemlist, list):
        itemlist = [itemlist]

    hash_object = hashlib.md5()
    for item in itemlist:
        hash_object.update(item.encode("utf-8"))
    return hash_object.hexdigest()


def generate_datalad_identifier(stack, exc):
    """the generation of the identifier for datalad is custom, meaning that
       we take our own subset of metadata and generate a custom identifier 
       (and helpme uses it verbatim). This means that we use:
       - exception class name
       - md5 of functions list up until datalad
       - md5 of functions for datalad

       Parameters
       ----------
       stack : list of str
         list of functions to extract from traceback
       exc: str
         the exception to derive the name from
    """
    # Regular expression to remove install directories
    install_dir = "(%s)" % "|".join(sys.path)

    # Derive a list with datalad, and a list without
    datald = []
    others = []
    for (filename, line, procname, text) in stack:
        if re.search(install_dir, filename):
            filename = re.sub(install_dir, "", filename).strip("/")
            if "datalad" in filename:
                datald.append(filename)
            else:
                others.append(filename)

    # Generate md5 of each, plus exception name
    return "%s-others-%s-datald-%s" % (
        type(exc).__name__,
        generate_identifier_hash(others),
        generate_identifier_hash(datald),
    )


def submit_helpme(title=None, tb="", detail="", identifier=None, repo=None):
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
       tb : str
         the full traceback
       identifier : str 
         the identifier string (will use traceback if not defined)
       repo : str
         GitHub repo (<username>/<repo>) to submit to.
    """
    title = title or default_title
    repo = repo or default_repo

    # Not providing a custom identifier means helpme generates it
    generate_md5 = False
    if identifier is None:
        identifier = tb
        generate_md5 = True

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
%s""" % (
                detail,
                tb,
                cmo.out,
            )

        # Submit the issue
        issue = helper.run_headless(
            repo=repo,
            body=body,
            title=title,
            identifier=identifier,
            generate_md5=generate_md5,
        )

    except ImportError:
        lgr.debug(
            "helpme is not installed to report issues: pip install helpme[github]"
        )
        pass
