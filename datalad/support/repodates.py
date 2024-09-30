# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Utilities for checking repository dates.
"""

import logging
import operator
import re
import time

from datalad.log import log_progress
from datalad.support.exceptions import CommandError
from datalad.support.gitrepo import GitRepo

lgr = logging.getLogger('datalad.repodates')


def _cat_blob(repo, obj, bad_ok=False):
    """Call `git cat-file blob OBJ`.

    Parameters
    ----------
    repo : GitRepo
    obj : str
        Blob object.
    bad_ok : boolean, optional
        Don't fail if `obj` doesn't name a known blob.

    Returns
    -------
    Blob's content (str) or None if `obj` is not and `bad_ok` is true.
    """
    if bad_ok:
        kwds = {"expect_fail": True, "expect_stderr": True}
    else:
        kwds = {}

    try:
        out_cat = repo.call_git(["cat-file", "blob", obj], read_only=True,
                                **kwds)
    except CommandError as exc:
        if bad_ok and "bad file" in exc.stderr:
            out_cat = None
        else:
            raise
    return out_cat


def branch_blobs(repo, branch):
    """Get all blobs for `branch`.

    Parameters
    ----------
    repo : GitRepo
    branch : str

    Returns
    -------
    A generator object that returns (hexsha, content, file name) for each blob
    in `branch`.  Note: By design a blob isn't tied to a particular file name;
    the returned file name matches what is returned by 'git rev-list'.
    """
    # Note: This might be nicer with rev-list's --filter and
    # --filter-print-omitted, but those aren't available until Git v2.16.
    lines = repo.call_git_items_(["rev-list", "--objects"] + [branch],
                                 read_only=True)
    # Trees and blobs have an associated path printed.
    objects = (ln.split() for ln in lines)
    blob_trees = [obj for obj in objects if len(obj) == 2]

    num_objects = len(blob_trees)

    log_progress(lgr.info, "repodates_branch_blobs",
                 "Checking %d objects", num_objects,
                 label="Checking objects", total=num_objects, unit=" objects")
    # This is inefficient.  It makes a git call for each object, some of which
    # aren't even blobs.  We could instead use 'git cat-file --batch'.
    for obj, fname in blob_trees:
        log_progress(lgr.info, "repodates_branch_blobs",
                     "Checking %s", obj,
                     increment=True, update=1)
        content = _cat_blob(repo, obj, bad_ok=True)
        if content:
            yield obj, content, fname
    log_progress(lgr.info, "repodates_branch_blobs",
                 "Finished checking %d objects", num_objects)


def branch_blobs_in_tree(repo, branch):
    """Get all blobs for the current tree of `branch`.

    Parameters
    ----------
    repo : GitRepo
    branch : str, optional

    Returns
    -------
    A generator object that returns (hexsha, content, file name) for each blob.
    Note: If there are multiple files in the tree that point to the blob, only
    the first file name that is reported by 'git ls-tree' is used (i.e., one
    entry per blob is yielded).
    """
    seen_blobs = set()
    lines = list(repo.call_git_items_(["ls-tree", "-z", "-r", branch],
                                      sep="\0", read_only=True))
    if lines:
        num_lines = len(lines)
        log_progress(lgr.info,
                     "repodates_blobs_in_tree",
                     "Checking %d objects in git-annex tree", num_lines,
                     label="Checking objects", total=num_lines,
                     unit=" objects")
        for line in lines:
            if not line:
                continue
            _, obj_type, obj, fname = line.split()
            log_progress(lgr.info, "repodates_blobs_in_tree",
                         "Checking %s", obj,
                         increment=True, update=1)
            if obj_type == "blob" and obj not in seen_blobs:
                yield obj, _cat_blob(repo, obj), fname
            seen_blobs.add(obj)
        log_progress(lgr.info, "repodates_blobs_in_tree",
                     "Finished checking %d blobs", num_lines)


# In uuid.log, timestamps look like "timestamp=1523283745.683191724s" and occur
# at the end of the line.  In the *.log and *.log.meta files that are
# associated with annexed files, the timestamps occur at beginning of the line
# and don't have the "timestamp=" prefix.
ANNEX_DATE_RE = re.compile(r"^(?:[^\n]+timestamp=)?([0-9]+)(?:\.[0-9]+)?s",
                           re.MULTILINE)


def search_annex_timestamps(text):
    """Extract unix timestamps content of the git-annex branch.

    Parameters
    ----------
    text : str
        Content from the git-annex branch (e.g., the content of the "uuid.log"
        file).

    Returns
    -------
    A generator object that returns a unix timestamp (without fractional any
    seconds) for each timestamp found in `text`.
    """
    for match in ANNEX_DATE_RE.finditer(text):
        yield int(match.group(1))


def annex_dates(repo, all_objects=True):
    """Get git-annex branch blobs containing dates.

    Parameters
    ----------
    repo : GitRepo
    all_objects : bool, optional
        Instead for searching the content of all blobs in the git-annex branch,
        search only the blobs that are in the tree of the tip of the git-annex
        branch.

    Returns
    -------
    A generator object that returns a tuple with the blob hexsha, a generator
    with the blob's timestamps, and an associated file name.
    """
    blob_fn = branch_blobs if all_objects else branch_blobs_in_tree
    for hexsha, content, fname in blob_fn(repo, "git-annex"):
        yield hexsha, search_annex_timestamps(content), fname


def tag_dates(repo, pattern=""):
    """Get timestamps for annotated tags.

    Parameters
    ----------
    repo : GitRepo
    pattern : str
        Limit the tags by this pattern. It will be appended to 'refs/tags'
        argument passed to `git for-each-ref`.

    Returns
    -------
    A generator object that returns a tuple with the tag hexsha and timestamp.
    """
    for rec in repo.for_each_ref_(
            fields=['objectname', 'taggerdate:raw'],
            pattern='refs/tags/' + pattern):
        if not rec['taggerdate:raw']:
            # There's not a tagger date. It's not an annotated tag.
            continue
        yield rec['objectname'], int(rec['taggerdate:raw'].split()[0])


def log_dates(repo, revs=None):
    """Get log timestamps.

    Parameters
    ----------
    repo : GitRepo
    revs : list, optional
        Extract timestamps from commit objects that are reachable from these
        revisions.

    Returns
    -------
    A generator object that returns a tuple with the commit hexsha, author
    timestamp, and committer timestamp.
    """
    opts = [] if revs else ["--branches"]
    try:
        for line in repo.get_revisions(revs, fmt="%H %at %ct", options=opts):
            hexsha, author_timestamp, committer_timestamp = line.split()
            yield hexsha, int(author_timestamp), int(committer_timestamp)
    except CommandError as e:
        # With some Git versions, calling `git log --{all,branches,remotes}` in
        # a repo with no commits may signal an error.
        if "does not have any commits yet" not in e.stderr:
            raise e


def check_dates(repo, timestamp=None, which="newer", revs=None,
                annex=True, tags=True):
    """Search for dates in `repo` that are newer than `timestamp`.

    This examines commit logs of local branches and the content of blobs in the
    git-annex branch.

    Parameters
    ----------
    repo : GitRepo or str
        If a str is passed, it is taken as the path to a GitRepo.
    timestamp : int, optional
        Unix timestamp.  It defaults to a day before now.
    which : {"newer", "older"}
        Whether to return timestamps that are newer or older than `timestamp`.
    revs : list, optional
        Search for commit timestamps in commits that are area reachable from
        these revisions. Any revision-specification allowed by `git log` can be
        used, including things like `--all`. Defaults to all local branches.
    annex : {True, "tree", False}, optional
        If True, search the content of all blobs in the git-annex branch.  If
        "tree", search only the blobs that are in the tree of the tip of the
        git-annex branch.  If False, do not search git-annex blobs.
    tags : bool, optional
        Whether to check dates the dates of annotated tags.

    Returns
    -------
    A dict that reports newer timestamps.
    """
    if isinstance(repo, str):
        repo = GitRepo(repo, create=False)

    if timestamp is None:
        timestamp = int(time.time()) - 60 * 60 * 24

    if which == "newer":
        cmp_fn = operator.gt
    elif which == "older":
        cmp_fn = operator.lt
    else:
        raise ValueError("unrecognized value for `which`: {}".format(which))

    results = {}

    lgr.debug("Checking dates in logs")
    for hexsha, a_timestamp, c_timestamp in log_dates(repo, revs=revs):
        if cmp_fn(a_timestamp, timestamp) or cmp_fn(c_timestamp, timestamp):
            results[hexsha] = {"type": "commit",
                               "author-timestamp": a_timestamp,
                               "committer-timestamp": c_timestamp}

    if tags:
        lgr.debug("Checking dates of annotated tags")
        for hexsha, tag_timestamp in tag_dates(repo):
            if cmp_fn(tag_timestamp, timestamp):
                results[hexsha] = {"type": "tag",
                                   "timestamp": tag_timestamp}

    if annex and "git-annex" in repo.get_branches():
        all_objects = annex != "tree"
        lgr.debug("Checking dates in blobs of git-annex branch%s",
                  "" if all_objects else "'s tip")
        for hexsha, timestamps, fname in annex_dates(repo, all_objects):
            hits = [ts for ts in timestamps if cmp_fn(ts, timestamp)]
            if hits:
                results[hexsha] = {"type": "annex-blob",
                                   "timestamps": hits,
                                   "filename": fname}

    return {"reference-timestamp": timestamp,
            "which": which,
            "objects": results}
