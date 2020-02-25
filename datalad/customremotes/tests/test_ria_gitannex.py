from datalad.api import (
    create,
)
from datalad.tests.utils import with_tempfile

from datalad.utils import Path
from datalad.tests.utils import (
    skip_if_on_windows,
    skip_ssh,
    slow
)
from datalad.customremotes.tests.ria_utils import (
    initexternalremote,
    skip_non_ssh,
)


@skip_if_on_windows
@skip_non_ssh  # superfluous in an SSH-run and annex-testremote is slow
@with_tempfile(mkdir=True)
@with_tempfile()
def test_gitannex_localio_url(path, objtree):
    ds = create(path)
    initexternalremote(
        ds.repo, 'ria-local', 'ria',
        config={'url': "ria+{}".format(Path(objtree).as_uri())})
    ds.repo._run_annex_command(
        'testremote',
        annex_options=['ria-local'],
        log_stdout=False,
    )


@slow
@skip_if_on_windows
@skip_ssh
@with_tempfile(mkdir=True)
@with_tempfile()
def test_gitannex_remoteio_url(path, objtree):
    ds = create(path)
    initexternalremote(
        ds.repo, 'ria-remote', 'ria',
        config={'url': "ria+ssh://datalad-test:{}".format(objtree)})
    ds.repo._run_annex_command(
        'testremote',
        annex_options=['ria-remote'],
        log_stdout=False,
    )
