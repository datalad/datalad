import os
import inspect
from glob import glob
from functools import wraps
from six import iteritems


from datalad.utils import Path
from datalad.tests.utils import (
    create_tree,
)

from nose import SkipTest
from nose.plugins.attrib import attr

example_payload = {
    'one.txt': 'content1',
    'subdir': {
        'two': 'content2',
    },
}


def get_all_files(path):
    return sorted([
        Path(p).relative_to(path)
        for p in glob(str(Path(path) / '**'), recursive=True)
        if not Path(p).is_dir()
    ])


# TODO think about migrating to AnnexRepo
def initremote(repo, name, encryption=None, config=None):
    cfg = dict(config) if config else {}
    cfg['encryption'] = encryption if encryption else 'none'
    args = [name]
    args += ['{}={}'.format(k, v) for k, v in iteritems(cfg)]
    repo._run_annex_command(
        'initremote',
        annex_options=args,
    )


def initexternalremote(repo, name, type, encryption=None, config=None):
    config = dict(
        config if config else {},
        type='external',
        externaltype=type,
    )
    return initremote(repo, name, encryption=encryption, config=config)


def setup_archive_remote(repo, archive_path):

    # for integration in a URL, we need POSIX version of the path
    archive_path = Path(archive_path)

    if 'RIA_TESTS_SSH' in os.environ:
        cfg = {'url': 'ria+ssh://datalad-test{}'.format(archive_path.as_posix())}
    else:
        cfg = {'url': 'ria+{}'.format(archive_path.as_uri())}
    initexternalremote(repo, 'archive', 'ria', config=cfg)


def populate_dataset(ds):
    create_tree(ds.path, example_payload)


def check_not_generatorfunction(func):
    """Internal helper to verify that we are not decorating generator tests"""
    if inspect.isgeneratorfunction(func):
        raise RuntimeError("{}: must not be decorated, is a generator test"
                           .format(func.__name__))


def skip_ssh(func):
    """Skips SSH-based tests if environment variable RIA_TESTS_SSH was not set
    """

    check_not_generatorfunction(func)

    @wraps(func)
    @attr('skip_ssh')
    def newfunc(*args, **kwargs):
        if 'RIA_TESTS_SSH' not in os.environ:
            raise SkipTest("Disabled, set RIA_TESTS_SSH to run")
        return func(*args, **kwargs)
    return newfunc


def skip_non_ssh(func):
    """Skips non-SSH-based tests if environment variable RIA_TESTS_SSH was set

    This is for test alternatives in order to blow runtime of SSH testing with tests that ran in other test builds.
    """

    check_not_generatorfunction(func)

    @wraps(func)
    @attr('skip_ssh')
    def newfunc(*args, **kwargs):
        if 'RIA_TESTS_SSH' in os.environ:
            raise SkipTest("Disabled, since RIA_TESTS_SSH is set")
        return func(*args, **kwargs)
    return newfunc
