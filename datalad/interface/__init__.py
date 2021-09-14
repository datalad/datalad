# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""High-level interface definition

"""

__docformat__ = 'restructuredtext'

# ORDER MATTERS FOLKS!

# the following should be series of import definitions for interface implementations
# that shall be exposed in the Python API and the cmdline interface
# all interfaces should be associated with (at least) one of the groups below
_group_dataset = (
    'Commands for dataset operations',
    [
        # source module, source object[, dest. cmdline name[, dest python name]]
        # src module can be relative, but has to be relative to the main 'datalad' package
        ('datalad.core.local.create', 'Create'),
        ('datalad.distribution.install', 'Install'),
        ('datalad.distribution.get', 'Get'),
        ('datalad.core.distributed.push', 'Push', 'push'),
        ('datalad.distribution.uninstall', 'Uninstall', 'uninstall', 'uninstall'),
        ('datalad.distribution.drop', 'Drop', 'drop', 'drop'),
        ('datalad.distribution.remove', 'Remove', 'remove', 'remove'),
        # N/I ATM
        # ('datalad.distribution.move', 'Move'),
        ('datalad.distribution.update', 'Update'),
        ('datalad.distribution.create_sibling',
         'CreateSibling',
         'create-sibling'),
        ('datalad.distribution.create_sibling_github',
         'CreateSiblingGithub',
         'create-sibling-github'),
        ('datalad.distributed.create_sibling_gitlab',
         'CreateSiblingGitlab',
         'create-sibling-gitlab'),
        ('datalad.distributed.create_sibling_ria',
         'CreateSiblingRia',
         'create-sibling-ria'),
        ('datalad.interface.unlock', 'Unlock', 'unlock'),
        ('datalad.core.local.save', 'Save', 'save'),
        ('datalad.local.copy_file', 'CopyFile', 'copy-file'),
    ])

_group_metadata = (
    'Commands for metadata handling',
    [
        ('datalad.metadata.search', 'Search',
         'search', 'search'),
        ('datalad.metadata.metadata', 'Metadata',
         'metadata'),
        ('datalad.metadata.aggregate', 'AggregateMetaData',
         'aggregate-metadata', 'aggregate_metadata'),
        ('datalad.metadata.extract_metadata', 'ExtractMetadata',
         'extract-metadata', 'extract_metadata'),
    ])

_group_misc = (
    'Miscellaneous commands',
    [
        ('datalad.local.wtf', 'WTF'),
        ('datalad.local.no_annex', 'NoAnnex'),
        ('datalad.local.add_readme', 'AddReadme'),
        ('datalad.local.addurls', 'Addurls'),
        ('datalad.local.check_dates', 'CheckDates'),
        ('datalad.local.export_archive', 'ExportArchive'),
        ('datalad.distributed.export_to_figshare', 'ExportToFigshare'),
        ('datalad.interface.test', 'Test'),
        ('datalad.interface.clean', 'Clean'),
        ('datalad.interface.add_archive_content', 'AddArchiveContent',
         'add-archive-content'),
        ('datalad.interface.download_url', 'DownloadURL', 'download-url'),
        ('datalad.interface.shell_completion', 'ShellCompletion', 'shell-completion'),
        ('datalad.core.local.run', 'Run', 'run'),
        ('datalad.interface.rerun', 'Rerun', 'rerun'),
        ('datalad.interface.run_procedure', 'RunProcedure', 'run-procedure'),
        ('datalad.distributed.export_archive_ora', 'ExportArchiveORA',
         'export-archive-ora')
    ])

_group_plumbing = (
    'Plumbing commands',
    [
        ('datalad.interface.annotate_paths', 'AnnotatePaths', 'annotate-paths'),
        ('datalad.core.distributed.clone', 'Clone'),
        ('datalad.distribution.create_test_dataset', 'CreateTestDataset',
         'create-test-dataset'),
        ('datalad.core.local.status', 'Status', 'status'),
        ('datalad.core.local.diff', 'Diff', 'diff'),
        ('datalad.distribution.siblings', 'Siblings', 'siblings'),
        ('datalad.support.sshrun', 'SSHRun', 'sshrun'),
        ('datalad.local.subdatasets', 'Subdatasets', 'subdatasets'),
    ])


# Some known extensions and their commands to suggest whenever lookup fails
_known_extension_commands = {
    'datalad-container': ('containers-list', 'containers-remove', 'containers-add', 'containers-run'),
    'datalad-crawler': ('crawl', 'crawl-init'),
    'datalad-deprecated': ('ls',),
    'datalad-neuroimaging': ('bids2scidata',)
}


_deprecated_commands = {
    'add': "save",
}
