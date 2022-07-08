# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

import inspect
import os
from functools import wraps
from glob import glob

from datalad.tests.utils_pytest import (
    SkipTest,
    attr,
    create_tree,
)
from datalad.utils import Path

common_init_opts = ["encryption=none", "type=external", "externaltype=ora",
                    "autoenable=true"]

example_payload = {
    'one.txt': 'content1',
    'subdir': {
        'two': 'content2',
    },
}


example_payload2 = {
    'three.txt': 'content3',
    'subdir': {
        'four': 'content4',
    },
}


def get_all_files(path):
    return sorted([
        Path(p).relative_to(path)
        for p in glob(str(Path(path) / '**'), recursive=True)
        if not Path(p).is_dir()
    ])


def initremote(repo, name, encryption=None, config=None):
    cfg = dict(config) if config else {}
    cfg['encryption'] = encryption if encryption else 'none'
    args = ['{}={}'.format(k, v) for k, v in cfg.items()]
    repo.init_remote(name, args)


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

    if 'DATALAD_TESTS_SSH' in os.environ:
        cfg = {'url': 'ria+ssh://datalad-test{}'
                      ''.format(archive_path.as_posix())}
    else:
        cfg = {'url': 'ria+{}'.format(archive_path.as_uri())}
    initexternalremote(repo, 'archive', 'ora', config=cfg)


def populate_dataset(ds):
    # create 2 commits
    for pl in [example_payload, example_payload2]:
        create_tree(ds.path, pl)
        ds.save()


def check_not_generatorfunction(func):
    """Internal helper to verify that we are not decorating generator tests"""
    if inspect.isgeneratorfunction(func):
        raise RuntimeError("{}: must not be decorated, is a generator test"
                           .format(func.__name__))


def skip_non_ssh(func):
    """Skips non-SSH-based tests if environment variable DATALAD_TESTS_SSH was
    set

    This is for test alternatives in order to blow runtime of SSH testing with
    tests that ran in other test builds.
    """

    check_not_generatorfunction(func)

    @wraps(func)
    @attr('skip_ssh')
    def  _wrap_skip_non_ssh(*args, **kwargs):
        if 'DATALAD_TESTS_SSH' in os.environ:
            raise SkipTest("Disabled, since DATALAD_TESTS_SSH is set")
        return func(*args, **kwargs)
    return  _wrap_skip_non_ssh
