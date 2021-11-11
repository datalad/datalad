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
# the name of the `_group_*` variable determines the sorting in the command overview
# alphanum ascending order
_group_0dataset = (
    'Essential commands',
    [
        # source module, source object[, dest. cmdline name[, dest python name]]
        # src module can be relative, but has to be relative to the main 'datalad' package
        ('datalad.core.local.create', 'Create'),
        ('datalad.core.local.save', 'Save', 'save'),
        ('datalad.core.local.status', 'Status', 'status'),
        ('datalad.core.distributed.clone', 'Clone'),
        ('datalad.distribution.get', 'Get'),
        ('datalad.core.distributed.push', 'Push', 'push'),
        ('datalad.core.local.run', 'Run', 'run'),
        ('datalad.core.local.diff', 'Diff', 'diff'),
    ])

_group_1siblings = (
    'Commands for collaborative workflows',
    [
        ('datalad.distributed.create_sibling_github', 'CreateSiblingGithub'),
        ('datalad.distributed.create_sibling_gitlab', 'CreateSiblingGitlab'),
        ('datalad.distributed.create_sibling_gogs', 'CreateSiblingGogs'),
        ('datalad.distributed.create_sibling_gin', 'CreateSiblingGin'),
        ('datalad.distributed.create_sibling_gitea', 'CreateSiblingGitea'),
        ('datalad.distributed.create_sibling_ria', 'CreateSiblingRia'),
        ('datalad.distribution.create_sibling', 'CreateSibling'),
        ('datalad.distribution.siblings', 'Siblings', 'siblings'),
        ('datalad.distribution.update', 'Update'),
    ])

_group_2dataset = (
    'Dataset operations',
    [
        ('datalad.local.addurls', 'Addurls'),
        ('datalad.local.clean', 'Clean'),
        ('datalad.local.copy_file', 'CopyFile'),
        ('datalad.local.download_url', 'DownloadURL'),
        ('datalad.distributed.drop', 'Drop'),
        ('datalad.local.export_archive', 'ExportArchive'),
        ('datalad.distributed.export_archive_ora', 'ExportArchiveORA'),
        ('datalad.distributed.export_to_figshare', 'ExportToFigshare'),
        ('datalad.distribution.install', 'Install'),
        ('datalad.local.remove', 'Remove'),
        ('datalad.local.rerun', 'Rerun'),
        ('datalad.local.run_procedure', 'RunProcedure'),
        ('datalad.local.subdatasets', 'Subdatasets'),
        ('datalad.distribution.uninstall', 'Uninstall'),
        ('datalad.local.unlock', 'Unlock'),
    ])

_group_2metadata = (
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

_group_3misc = (
    'Miscellaneous commands',
    [
        ('datalad.local.wtf', 'WTF'),
        ('datalad.local.no_annex', 'NoAnnex'),
        ('datalad.local.add_readme', 'AddReadme'),
        ('datalad.local.check_dates', 'CheckDates'),
        ('datalad.local.add_archive_content', 'AddArchiveContent'),
    ])

_group_4plumbing = (
    'Plumbing commands',
    [
        ('datalad.distribution.create_test_dataset', 'CreateTestDataset',
         'create-test-dataset'),
        ('datalad.support.sshrun', 'SSHRun', 'sshrun'),
        ('datalad.interface.test', 'Test'),
        ('datalad.interface.shell_completion', 'ShellCompletion', 'shell-completion'),
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
    'uninstall': 'drop',
}
