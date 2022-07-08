"""Utils for cached test datasets"""

from datalad import cfg
from datalad.core.distributed.clone import Clone
from datalad.distribution.dataset import Dataset
from datalad.support.annexrepo import AnnexRepo
from datalad.tests.utils_pytest import (
    DEFAULT_REMOTE,
    with_tempfile,
)
from datalad.utils import (
    Path,
    better_wraps,
    ensure_list,
    optional_args,
    rmtree,
)

DATALAD_TESTS_CACHE = cfg.obtain("datalad.tests.cache")


def url2filename(url):
    """generate file/directory name from a URL"""

    # TODO: Not really important for now, but there should be a more
    #       sophisticated approach to replace. May be just everything that
    #       isn't alphanumeric? Or simply hash the URL?
    #       URL: Will include version eventually. Would need parsing to hash
    #       w/o any parameters. Having separate clones per requested version
    #       would defy point of cache, particularly wrt downloading content.
    #       Depends on usecase, of course, but immediate one is about container
    #       images -> not cheap.
    # make it a Path, too, so pathlib can raise if we are creating an invalid
    # path on some system we run the tests on.
    return Path(
        url.lower().replace("/", "_").replace(":", "_").replace("?", "_"))


def get_cached_dataset(url, version=None, keys=None):
    """ Helper to get a cached clone from url

    Intended for use from within `cached_dataset` and `cached_url` decorators.
    Clones `url` into user's cache under datalad/tests/`name`. If such a clone
    already exists, don't clone but return the existing one. So, it's supposed
    to cache the original source in order to reduce time and traffic for tests,
    by letting subsequent requests clone from a local location directly.

    If it's an annex get the content as provided by `keys`, too.
    Note, that as a transparent cache replacing the repo at URL from the POV of
    a test, we can't address content via paths, since those are valid only with
    respect to a particular worktree. If different tests clone from the same
    cached dataset, each requesting different versions and different paths
    thereof, we run into trouble if the cache itself checks out a particular
    requested version.

    Verifies that `version` can be checked out, but doesn't actually do it,
    since the cached dataset is intended to be used as origin instead of the
    original remote at URL by the `cached_dataset` test decorator. Checkout of
    a particular version should happen in its clone.

    Parameters
    ----------
    url: str
        URL to clone from
    keys: str or list or None
        (list of) annex keys to get content for.
    version: str or None
        A commit or an object that can be dereferenced to one.

    Returns
    -------
    Dataset
    """

    # TODO: What about recursive? Might be complicated. We would need to make
    #       sure we can recursively clone _from_ here then, potentially
    #       requiring submodule URL rewrites. Not sure about that ATM.

    # TODO: Given that it is supposed to be a cache for the original repo at
    #       `url`, we prob. should make this a bare repository. We don't need
    #       a potentially expensive checkout here. Need to double check
    #       `annex-get --key` in bare repos, though. Plus datalad-clone doesn't
    #       have --bare yet. But we want all the annex/special-remote/ria magic
    #       of datalad. So, plain git-clone --bare is not an option.

    if not DATALAD_TESTS_CACHE:
        raise ValueError("Caching disabled by config")

    ds = Dataset(DATALAD_TESTS_CACHE / url2filename(url))

    if not ds.is_installed():
        ds = Clone()(url, ds.pathobj)

    # When/How to update a dataset in cache? If version is a commit SHA and we
    # have it, there's no need for an update. Otherwise it gets tricky, because
    # this is a cache, not a checkout a test would operate on. It needs to
    # behave as if it was the thing at `url` from the point of view of the test
    # using it (cloning/getting content from here). We would need to update all
    # references, not just fetch them!
    #
    # Can we even (cheaply) tell whether `version` is an absolute reference
    # (actual SHA, not a branch/tag)?
    #
    # NOTE: - consider git-clone --mirror, but as w/ --bare: not an option for
    #         datalad-clone yet.
    #       - --reference[-if-able] might also be worth thinking about for
    #         the clone @cached_dataset creates wrt clone in cacheq
    #
    # So, for now fetch, figure whether there actually was something to fetch
    # and if so simply invalidate cache and re-clone/get. Don't overcomplicate
    # things. It's about datasets used in the tests - they shouldn't change too
    # frequently.
    elif any('uptodate' not in c['operations']
             for c in ds.repo.fetch(DEFAULT_REMOTE)):
        rmtree(ds.path)
        ds = Clone()(url, ds.pathobj)

    if version:
        # check whether version is available
        assert ds.repo.commit_exists(version)
    if keys and AnnexRepo.is_valid_repo(ds.path):
        ds.repo.get(keys, key=True)

    return ds


@optional_args
def cached_dataset(f, url=None, version=None, paths=None):
    """Test decorator providing a clone of `url` from cache

    If config datalad.tests.cache is not set, delivers a clone in a temporary
    location of the original `url`. Otherwise that clone is in fact a clone of a
    cached dataset (origin being the cache instead of `url`).
    This allows to reduce time and network traffic when using a dataset in
    different tests.

    The clone will checkout `version` and get the content for `paths`.

    Parameters
    ----------
    url: str
        URL to the to be cloned dataset
    version: str
        committish to checkout in the clone
    paths: str or list
        annexed content to get

    Returns
    -------
    Dataset
        a clone of the dataset at `url` at a temporary location (cleaned up,
        after decorated test is finished - see with_tempfile). If caching is
        enabled, it's actually a clone of a clone, 'origin' being the clone in
        cache rather than the original repo at `url`.
    """
    @better_wraps(f)
    @with_tempfile
    def  _wrap_cached_dataset(*arg, **kw):

        if DATALAD_TESTS_CACHE:
            # Note: We can't pass keys based on `paths` parameter to
            # get_cached_dataset yet, since translation to keys depends on a
            # worktree. We'll have the worktree of `version` only after cloning.
            ds = get_cached_dataset(url, version=version)
            clone_ds = Clone()(ds.pathobj, arg[-1])
        else:
            clone_ds = Clone()(url, arg[-1])
        #save some cycles
        clone_repo = clone_ds.repo
        if version:
            clone_repo.checkout(version)
        if paths and AnnexRepo.is_valid_repo(clone_ds.path):
            # just assume ds is annex as well. Otherwise `Clone` wouldn't
            # work correctly - we don't need to test its implementation here
            if DATALAD_TESTS_CACHE:
                # cache is enabled; we need to make sure it has the desired
                # content, so clone_ds can get it from there. However, we got
                # `paths` and potentially a `version` they refer to. We can't
                # assume the same (or any) worktree in cache. Hence we need to
                # translate to keys.
                # MIH Despite the variable names used in this function
                # (pathS, keyS) they ultimately are passed to get(..., key=True)
                # which means that it can ever only be a single path and a
                # single key -- this is very confusing.
                # the key determination could hence be done with
                # get_file_annexinfo() in a much simpler way, but it seems this
                # function wants to be ready for more, sigh
                keys = [
                    p['key']
                    for p in clone_repo.get_content_annexinfo(
                        ensure_list(paths), init=None).values()
                    if 'key' in p
                ]
                if keys:
                    ds.repo.get(keys, key=True)
                clone_repo.fsck(remote=DEFAULT_REMOTE, fast=True)

            clone_ds.get(paths)
        return f(*(arg[:-1] + (clone_ds,)), **kw)

    return  _wrap_cached_dataset


@optional_args
def cached_url(f, url=None, keys=None):
    """Test decorator providing a URL to clone from, pointing to cached dataset

    If config datalad.tests.cache is not set, delivers the original `url`,
    otherwise a file-scheme url to the cached clone thereof.

    Notes
    -----

    While this is similar to `cached_dataset`, there are important differences.

    1. As we deliver an URL, `version` parameter is irrelevant. The only
       relevant notion of version would need to be included in the URL

    2. We cannot request particular paths to be present in cache, since we
       a version to refer to by those paths. Therefore keys need to be
       specified.

    Parameters
    ----------
    url: str
        URL to the original dataset
    keys: str or list or None
        (list of) annex keys to get content for.

    Returns
    -------
    str
        URL to the cached dataset or the original URL if caching was disabled
    """

    # TODO: See Notes 1.)
    #       Append fragments/parameters of `url` to what we return -
    #       depending on how we generally decide to address versioned
    #       URLs for clone etc.

    @better_wraps(f)
    def  _wrap_cached_url(*arg, **kw):
        if DATALAD_TESTS_CACHE:
            ds = get_cached_dataset(url, version=None)
            if keys:
                ds.repo.get(keys, key=True)
            new_url = ds.pathobj.as_uri()
        else:
            new_url = url

        return f(*(arg + (new_url,)), **kw)

    return  _wrap_cached_url
