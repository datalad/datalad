# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Extension for checking dates within repositories."""

import json
import logging
import os
import time

from datalad.interface.base import (
    Interface,
    build_doc,
)
from datalad.interface.results import get_status_dict
from datalad.support.exceptions import (
    CapturedException,
    InvalidGitRepositoryError,
    MissingExternalDependency,
)

__docformat__ = "restructuredtext"

lgr = logging.getLogger("datalad.local.check_dates")


def _git_repos(paths):
    for path in paths:
        for root, dirs, _ in os.walk(path):
            if any(d == ".git" for d in dirs):
                yield root


def _parse_date(date):
    if date.startswith("@"):  # unix timestamp
        timestamp = int(date[1:])
    else:
        try:
            import dateutil.parser
        except ImportError:
            raise MissingExternalDependency(
                "python-dateutil",
                msg="This package is required to parse non-timestamp dates")

        from calendar import timegm

        # Note: datetime.timestamp isn't available in Python 2.
        try:
            timestamp = timegm(dateutil.parser.parse(date).utctimetuple())
        except TypeError as exc:
            # Make older dateutil versions return a consistent error for
            # invalid dates.
            raise ValueError(exc)
    return timestamp


@build_doc
class CheckDates(Interface):
    """Find repository dates that are more recent than a reference date.

    The main purpose of this tool is to find "leaked" real dates in
    repositories that are configured to use fake dates. It checks dates from
    three sources: (1) commit timestamps (author and committer dates), (2)
    timestamps within files of the "git-annex" branch, and (3) the timestamps
    of annotated tags.
    """
    import datalad.support.ansi_colors as ac
    from datalad.interface.base import eval_results
    from datalad.support.constraints import (
        EnsureChoice,
        EnsureNone,
        EnsureStr,
    )
    from datalad.support.param import Parameter

    result_renderer = "tailored"

    @staticmethod
    def custom_result_renderer(res, **kwargs):
        """Like 'json_pp', but skip non-error results without flagged objects.
        """
        # FIXME: I think the proper way to do this is to use 'result_filter',
        # but I couldn't seem to get eval_results to detect the filter when I
        # used
        #
        #      result_renderer = "json_pp"
        #      result_filter = lambda x: ...
        #
        # Also, I want to keep the "message" key for errors.
        from datalad.ui import ui
        to_render = {}
        if res["status"] == "error":
            to_render = dict(res.items())
        elif "report" in res and res["report"]["objects"]:
            to_render = {k: v for k, v in res.items()
                         if k not in ["status", "message", "logger"]}
        if to_render:
            ui.message(json.dumps(to_render, sort_keys=True, indent=2,
                                  default=str)
                       )

    _params_ = dict(
        paths=Parameter(
            args=("paths",),
            metavar="PATH",
            nargs="*",
            doc="""Root directory in which to search for Git repositories. The
            current working directory will be used by default.""",
            constraints=EnsureStr() | EnsureNone()),
        reference_date=Parameter(
            args=("-D", "--reference-date"),
            metavar="DATE",
            doc="""Compare dates to this date. If dateutil is installed, this
            value can be any format that its parser recognizes. Otherwise, it
            should be a unix timestamp that starts with a "@". The default
            value corresponds to 01 Jan, 2018 00:00:00 -0000.""",
            constraints=EnsureStr()),
        revs=Parameter(
            args=("--rev",),
            dest="revs",
            action="append",
            metavar="REVISION",
            doc="""Search timestamps from commits that are reachable from [PY:
            these revisions PY][CMD: REVISION CMD]. Any revision specification
            supported by :command:`git log`, including flags like --all and
            --tags, can be used.[CMD:  This option can be given multiple times.
            CMD]"""),
        annex=Parameter(
            args=("--annex",),
            doc="""Mode for "git-annex" branch search. If 'all', all blobs
            within the branch are searched. 'tree' limits the search to blobs
            that are referenced by the tree at the tip of the branch. 'none'
            disables search of "git-annex" blobs.""",
            constraints=EnsureChoice("all", "tree", "none")),
        no_tags=Parameter(
            args=("--no-tags",),
            action="store_true",
            doc="""Don't check the dates of annotated tags."""),
        older=Parameter(
            args=("--older",),
            action="store_true",
            doc="""Find dates which are older than the reference date rather
            than newer."""),
    )

    @staticmethod
    @eval_results
    def __call__(paths,
                 *,
                 reference_date="@1514764800",
                 revs=None,
                 annex="all",
                 no_tags=False,
                 older=False):
        from datalad.support.repodates import check_dates

        which = "older" if older else "newer"

        try:
            ref_ts = _parse_date(reference_date)
        except ValueError as exc:
            lgr.error("Could not parse '%s' as a date", reference_date)
            ce = CapturedException(exc)
            yield get_status_dict("check_dates",
                                  status="error",
                                  message=str(ce),
                                  exception=ce)
            return

        lgr.info("Searching for dates %s than %s",
                 which,
                 time.strftime("%d %b %Y %H:%M:%S +0000", time.gmtime(ref_ts)))

        for repo in _git_repos(paths or ["."]):
            fullpath = os.path.abspath(repo)
            lgr.debug("Checking %s", fullpath)

            try:
                report = check_dates(repo,
                                     ref_ts,
                                     which=which,
                                     revs=revs or ["--all"],
                                     annex={"all": True,
                                            "none": False,
                                            "tree": "tree"}[annex],
                                     tags=not no_tags)
            except InvalidGitRepositoryError as exc:
                lgr.warning("Skipping invalid Git repo: %s", repo)
                continue

            yield get_status_dict(
                "check_dates",
                status="ok",
                path=fullpath,
                message=("Found {} dates" if report["objects"]
                         else "No {} dates found").format(which),
                report=report)
