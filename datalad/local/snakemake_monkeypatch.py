from snakemake.io import (
    _IOFile as SnakeMakeIOFile,
)


class DataLadSnakeMakeIOFile(SnakeMakeIOFile):

    __slots__ = SnakeMakeIOFile.__slots__ + ["_datalad_dataset"]

    def inventory(self):
        # the idea is: Whenever snakemake inspects a file for
        # properties (exists, mtime, etc.) it should call this
        # function first to harvest that information efficiently.
        # we can hook into this, and make sure that the file
        # that is to be inspected is actually present
        self._datalad_dataset.get(
            self.file,
            on_failure='ignore')
        return SnakeMakeIOFile.inventory(self)
