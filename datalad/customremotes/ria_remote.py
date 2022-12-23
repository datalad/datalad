from datalad.customremotes.main import main as super_main
from datalad.distributed.ora_remote import ORARemote
from datalad.support.annexrepo import AnnexRepo


class DeprecatedRIARemote(ORARemote):
    """This is a shim for backwards compatibility with the old and archived
    git-annex-ria-remote, which the current ORA remote is based on. Providing
    this remote allows datasets that are configured with the old name (and the
    respective config names) to still work.
    However, this is intended to be somewhat temporary and be replaced by
    another implementation that actually migrates from ria to ora once we
    settled for an approach.
    """

    def __init__(self, annex):
        super().__init__(annex)

    def initremote(self):
        self.message("special remote type 'ria' is deprecated. Consider "
                     "migrating to 'ora'.", type='info')
        super().initremote(self)

    def _load_local_cfg(self):
        """Overwrite _load_local_cfg in order to initialize attributes with
        deprecated 'ria' configs if they exist and then go on to let 'super' do
        it's thing"""
        self._repo = AnnexRepo(self.gitdir)
        self.storage_host = \
            self._repo.config.get(f"annex.ria-remote.{self.name}.ssh-host")
        self.store_base_path = \
            self._repo.config.get(f"annex.ria-remote.{self.name}.base-path")
        self.force_write = \
            self._repo.config.get(f"annex.ria-remote.{self.name}.force-write")
        self.ignore_remote_config = \
            self._repo.config.get(f"annex.ria-remote.{self.name}.ignore-remote-config")
        super()._load_local_cfg()


def main():
    """cmdline entry point"""
    super_main(
        cls=DeprecatedRIARemote,
        remote_name='ria',
        description=\
        "transport file content to and from datasets hosted in RIA stores",
    )
