# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
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

from six import string_types

from datalad.support.gitrepo import GitRepo, GitCommandError

lgr = logging.getLogger('datalad.repodates')


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
    git = repo.repo.git
    # Note: This might be nicer with rev-list's --filter and
    # --filter-print-omitted, but those aren't available until Git v2.16.
    lines = git.rev_list(branch, objects=True).splitlines()
    # Trees and blobs have an associated path printed.
    objects = (ln.split() for ln in lines)
    blob_trees = (obj for obj in objects if len(obj) == 2)

    # This is inefficient.  It makes a git call for each object, some of which
    # aren't even blobs.  We could instead use 'git cat-file --batch'.
    for obj, fname in blob_trees:
        try:
            yield obj, git.cat_file("blob", obj), fname
        except GitCommandError:  # The object was a tree.
            continue


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
    git = repo.repo.git
    tree_lines = git.ls_tree(branch, z=True, r=True)
    if tree_lines:
        for line in tree_lines.strip("\0").split("\0"):
            _, obj_type, obj, fname = line.split()
            if obj_type == "blob" and obj not in seen_blobs:
                yield obj, git.cat_file("blob", obj), fname
            seen_blobs.add(obj)


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
    revs = revs or ["--branches"]
    try:
        for line in repo.repo.git.log(*revs, format="%H %at %ct").splitlines():
            hexsha, author_timestamp, committer_timestamp = line.split()
            yield hexsha, int(author_timestamp), int(committer_timestamp)
    except GitCommandError as e:
        # With some Git versions, calling `git log --{all,branches,remotes}` in
        # a repo with no commits may signal an error.
        if "does not have any commits yet" in e.stderr:
            return None
        raise e

def check_dates(repo, timestamp=None, which="newer", annex=True):
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
    annex : {True, "tree", False}, optional
        If True, search the content of all blobs in the git-annex branch.  If
        "tree", search only the blobs that are in the tree of the tip of the
        git-annex branch.  If False, do not search git-annex blobs.

    Returns
    -------
    A dict that reports newer timestamps.
    """
    if isinstance(repo, string_types):
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
    for hexsha, a_timestamp, c_timestamp in log_dates(repo):
        if cmp_fn(a_timestamp, timestamp) or cmp_fn(c_timestamp, timestamp):
            results[hexsha] = {"type": "commit",
                               "author-timestamp": a_timestamp,
                               "committer-timestamp": c_timestamp}

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
