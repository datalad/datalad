"""Testing cached test dataset utils"""

from unittest.mock import patch

from datalad.distribution.dataset import Dataset
from datalad.support.annexrepo import AnnexRepo
from datalad.support.gitrepo import GitRepo
from datalad.tests.utils_cached_dataset import (
    cached_dataset,
    cached_url,
    get_cached_dataset,
    url2filename,
)
from datalad.tests.utils_pytest import (
    DEFAULT_REMOTE,
    assert_equal,
    assert_false,
    assert_in,
    assert_is,
    assert_is_instance,
    assert_not_equal,
    assert_not_in,
    assert_raises,
    assert_result_count,
    assert_true,
    skip_if_no_network,
    with_tempfile,
)
from datalad.utils import (
    Path,
    ensure_list,
    opj,
)

CACHE_PATCH_STR = "datalad.tests.utils_cached_dataset.DATALAD_TESTS_CACHE"
CLONE_PATCH_STR = "datalad.tests.utils_cached_dataset.Clone.__call__"


@skip_if_no_network
@with_tempfile(mkdir=True)
def test_get_cached_dataset(cache_dir=None):

    # patch DATALAD_TESTS_CACHE to not use the actual cache with
    # the test testing that very cache.
    cache_dir = Path(cache_dir)

    # store file-based values for testrepo-minimalds for readability:
    annexed_file = opj('inannex', 'animated.gif')
    annexed_file_key = "MD5E-s144625--4c458c62b7ac8ec8e19c8ff14b2e34ad.gif"

    with patch(CACHE_PATCH_STR, new=cache_dir):

        # tuples to test (url, version, keys, class):
        test_cases = [

            # a simple testrepo
            ("https://github.com/datalad/testrepo--minimalds",
             "541cf855d13c2a338ff2803d4488daf0035e568f",
             None,
             AnnexRepo),
            # Same repo, but request paths to be present. This should work
            # with a subsequent call, although the first one did not already
            # request any:
            ("https://github.com/datalad/testrepo--minimalds",
             "9dd8b56cc706ab56185f2ceb75fbe9de9b606724",
             annexed_file_key,
             AnnexRepo),
            # Same repo again, but invalid version
            ("https://github.com/datalad/testrepo--minimalds",
             "nonexistent",
             "irrelevantkey",  # invalid version; don't even try to get the key
             AnnexRepo),
            # same thing with different name should be treated as a new thing:
            ("https://github.com/datalad/testrepo--minimalds",
             "git-annex",
             None,
             AnnexRepo),
            # try a plain git repo to make sure we can deal with that:
            # Note, that we first need a test case w/o a `key` parameter to not
            # blow up the test when Clone is patched, resulting in a MagicMock
            # instead of a Dataset instance within get_cached_dataset. In the
            # second case it's already cached then, so the patched Clone is
            # never executed.
            ("https://github.com/datalad/datalad.org",
             None,
             None,
             GitRepo),
            ("https://github.com/datalad/datalad.org",
             "gh-pages",
             "ignored-key",  # it's a git repo; don't even try to get a key
             GitRepo),

        ]
        for url, version, keys, cls in test_cases:
            target = cache_dir / url2filename(url)

            # assuming it doesn't exist yet - patched cache dir!
            in_cache_before = target.exists()
            with patch(CLONE_PATCH_STR) as exec_clone:
                try:
                    ds = get_cached_dataset(url, version, keys)
                    invalid_version = False
                except AssertionError:
                    # should happen only if `version` wasn't found. Implies
                    # that the dataset exists in cache (although not returned
                    # due to exception)
                    assert_true(version)
                    assert_false(Dataset(target).repo.commit_exists(version))
                    # mark for later assertions (most of them should still hold
                    # true)
                    invalid_version = True

            assert_equal(exec_clone.call_count, 0 if in_cache_before else 1)

            # Patch prevents actual execution. Now do it for real. Note, that
            # this might be necessary for content retrieval even if dataset was
            # in cache before.
            try:
                ds = get_cached_dataset(url, version, keys)
            except AssertionError:
                # see previous call
                assert_true(invalid_version)

            assert_is_instance(ds, Dataset)
            assert_true(ds.is_installed())
            assert_equal(target, ds.pathobj)
            assert_is_instance(ds.repo, cls)

            if keys and not invalid_version and \
                    AnnexRepo.is_valid_repo(ds.path):
                # Note: it's not supposed to get that content if passed
                # `version` wasn't available. get_cached_dataset would then
                # raise before and not download anything only to raise
                # afterwards.
                here = ds.config.get("annex.uuid")
                where = ds.repo.whereis(ensure_list(keys), key=True)
                assert_true(all(here in remotes for remotes in where))

            # version check. Note, that all `get_cached_dataset` is supposed to
            # do, is verifying, that specified version exists - NOT check it
            # out"
            if version and not invalid_version:
                assert_true(ds.repo.commit_exists(version))

            # re-execution
            with patch(CLONE_PATCH_STR) as exec_clone:
                try:
                    ds2 = get_cached_dataset(url, version, keys)
                except AssertionError:
                    assert_true(invalid_version)
            exec_clone.assert_not_called()
            # returns the same Dataset as before:
            assert_is(ds, ds2)


@skip_if_no_network
@with_tempfile(mkdir=True)
def test_cached_dataset(cache_dir=None):

    # patch DATALAD_TESTS_CACHE to not use the actual cache with
    # the test testing that very cache.
    cache_dir = Path(cache_dir)
    ds_url = "https://github.com/datalad/testrepo--minimalds"
    name_in_cache = url2filename(ds_url)
    annexed_file = Path("inannex") / "animated.gif"

    with patch(CACHE_PATCH_STR, new=cache_dir):

        @cached_dataset(url=ds_url)
        def decorated_test1(ds):
            # we get a Dataset instance
            assert_is_instance(ds, Dataset)
            # it's a clone in a temp. location, not within the cache
            assert_not_in(cache_dir, ds.pathobj.parents)
            assert_result_count(ds.siblings(), 1, type="sibling",
                                name=DEFAULT_REMOTE,
                                url=(cache_dir / name_in_cache).as_posix())
            here = ds.config.get("annex.uuid")
            origin = ds.config.get(f"remote.{DEFAULT_REMOTE}.annex-uuid")
            where = ds.repo.whereis(str(annexed_file))
            assert_not_in(here, where)
            assert_not_in(origin, where)

            return ds.pathobj, ds.repo.pathobj

        @cached_dataset(url=ds_url, paths=str(annexed_file))
        def decorated_test2(ds):
            # we get a Dataset instance
            assert_is_instance(ds, Dataset)
            # it's a clone in a temp. location, not within the cache
            assert_not_in(cache_dir, ds.pathobj.parents)
            assert_result_count(ds.siblings(), 1, type="sibling",
                                name=DEFAULT_REMOTE,
                                url=(cache_dir / name_in_cache).as_posix())
            here = ds.config.get("annex.uuid")
            origin = ds.config.get(f"remote.{DEFAULT_REMOTE}.annex-uuid")
            where = ds.repo.whereis(str(annexed_file))
            assert_in(here, where)
            assert_in(origin, where)

            return ds.pathobj, ds.repo.pathobj

        @cached_dataset(url=ds_url)
        def decorated_test3(ds):
            # we get a Dataset instance
            assert_is_instance(ds, Dataset)
            # it's a clone in a temp. location, not within the cache
            assert_not_in(cache_dir, ds.pathobj.parents)
            assert_result_count(ds.siblings(), 1, type="sibling",
                                name=DEFAULT_REMOTE,
                                url=(cache_dir / name_in_cache).as_posix())
            # origin is the same cached dataset, that got this content in
            # decorated_test2 before. Should still be there. But "here" we
            # didn't request it
            here = ds.config.get("annex.uuid")
            origin = ds.config.get(f"remote.{DEFAULT_REMOTE}.annex-uuid")
            where = ds.repo.whereis(str(annexed_file))
            assert_not_in(here, where)
            assert_in(origin, where)

            return ds.pathobj, ds.repo.pathobj

        @cached_dataset(url=ds_url,
                        version="541cf855d13c2a338ff2803d4488daf0035e568f")
        def decorated_test4(ds):
            # we get a Dataset instance
            assert_is_instance(ds, Dataset)
            # it's a clone in a temp. location, not within the cache
            assert_not_in(cache_dir, ds.pathobj.parents)
            assert_result_count(ds.siblings(), 1, type="sibling",
                                name=DEFAULT_REMOTE,
                                url=(cache_dir / name_in_cache).as_posix())
            # origin is the same cached dataset, that got this content in
            # decorated_test2 before. Should still be there. But "here" we
            # didn't request it
            here = ds.config.get("annex.uuid")
            origin = ds.config.get(f"remote.{DEFAULT_REMOTE}.annex-uuid")
            where = ds.repo.whereis(str(annexed_file))
            assert_not_in(here, where)
            assert_in(origin, where)

            assert_equal(ds.repo.get_hexsha(),
                         "541cf855d13c2a338ff2803d4488daf0035e568f")

            return ds.pathobj, ds.repo.pathobj

        first_dspath, first_repopath = decorated_test1()
        second_dspath, second_repopath = decorated_test2()
        decorated_test3()
        decorated_test4()

        # first and second are not the same, only their origin is:
        assert_not_equal(first_dspath, second_dspath)
        assert_not_equal(first_repopath, second_repopath)


@skip_if_no_network
@with_tempfile(mkdir=True)
def test_cached_url(cache_dir=None):

    # patch DATALAD_TESTS_CACHE to not use the actual cache with
    # the test testing that very cache.
    cache_dir = Path(cache_dir)

    ds_url = "https://github.com/datalad/testrepo--minimalds"
    name_in_cache = url2filename(ds_url)
    annexed_file = Path("inannex") / "animated.gif"
    annexed_file_key = "MD5E-s144625--4c458c62b7ac8ec8e19c8ff14b2e34ad.gif"

    with patch(CACHE_PATCH_STR, new=cache_dir):

        @cached_url(url=ds_url)
        def decorated_test1(url):
            # we expect a file-scheme url to a cached version of `ds_url`
            expect_origin_path = cache_dir / name_in_cache
            assert_equal(expect_origin_path.as_uri(),
                         url)
            origin = Dataset(expect_origin_path)
            assert_true(origin.is_installed())
            assert_false(origin.repo.file_has_content(str(annexed_file)))

        decorated_test1()

        @cached_url(url=ds_url, keys=annexed_file_key)
        def decorated_test2(url):
            # we expect a file-scheme url to a "different" cached version of
            # `ds_url`
            expect_origin_path = cache_dir / name_in_cache
            assert_equal(expect_origin_path.as_uri(),
                         url)
            origin = Dataset(expect_origin_path)
            assert_true(origin.is_installed())
            assert_true(origin.repo.file_has_content(str(annexed_file)))

        decorated_test2()

    # disable caching. Note, that in reality DATALAD_TESTS_CACHE is determined
    # on import time of datalad.tests.fixtures based on the config
    # "datalad.tests.cache". We patch the result here, not the config itself.
    with patch(CACHE_PATCH_STR, new=None):

        @cached_url(url=ds_url)
        def decorated_test3(url):
            # we expect the original url, since caching is disabled
            assert_equal(url, ds_url)

        decorated_test3()
