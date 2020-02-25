from datalad.api import (
    create,
)
import shutil
import subprocess
from datalad.tests.utils import (
    assert_in,
    assert_raises,
    assert_status,
    skip_if_on_windows,
    skip_ssh,
    with_tempfile,
)
from datalad.support.exceptions import CommandError

from datalad.customremotes.tests.ria_utils import (
    get_all_files,
    initexternalremote,
    populate_dataset,
)

from datalad.utils import Path


@skip_if_on_windows
@with_tempfile(mkdir=True)
@with_tempfile()
@with_tempfile()
def test_site_archive_location_config(path, objtree, objtree_alt):
    ds = create(path)
    # needs base-path under all circumstances
    assert_raises(
        CommandError,
        initexternalremote,
        ds.repo, 'archive', 'ria',
        config=None,
    )
    # specify archive location via config (could also be system-wide
    # config setting, done locally here for a simple test setup)
    ds.config.set('annex.ria-remote.archive.base-path', objtree, where='local')
    initexternalremote(
        ds.repo, 'archive', 'ria',
    )
    # put some stuff in and check if it flies
    populate_dataset(ds)
    ds.save()
    ds.repo.copy_to('.', 'archive')
    arxiv_files = get_all_files(objtree)
    assert len(arxiv_files) > 1


@skip_if_on_windows
@with_tempfile(mkdir=True)
@with_tempfile()
@with_tempfile()
def test_site_archive_url_config(path, objtree, objtree_alt):
    # same as test_site_archive_location_config but using an URL for configuration
    ds = create(path)
    # needs base-path under all circumstances
    assert_raises(
        CommandError,
        initexternalremote,
        ds.repo, 'archive', 'ria',
        config=None,
    )
    # specify archive location via URL + configured label (url...insteadOf) for reconfiguration
    ds.config.set('url.ria+{}.insteadOf'.format(Path(objtree).as_uri()),
                  'localstore:', where='local')
    initexternalremote(
        ds.repo, 'archive', 'ria', config={'url': 'localstore:'}
    )
    # put some stuff in and check if it flies
    populate_dataset(ds)
    ds.save()
    ds.repo.copy_to('.', 'archive')
    arxiv_files = get_all_files(objtree)
    assert len(arxiv_files) > 1

    # ensure we have stored the rewritten URL
    res = subprocess.run(['git', 'cat-file', 'blob', 'git-annex:remote.log'],
                         stdout=subprocess.PIPE, check=True,
                         cwd=str(ds.pathobj))
    assert_in("url=ria+{}".format(Path(objtree).as_uri()), res.stdout.decode())
