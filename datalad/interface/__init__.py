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
        ('datalad.distribution.create', 'Create'),
        ('datalad.distribution.install', 'Install'),
        ('datalad.distribution.get', 'Get'),
        ('datalad.distribution.add', 'Add'),
        ('datalad.distribution.publish', 'Publish'),
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
        ('datalad.distribution.add_sibling', 'AddSibling', 'add-sibling'),
        ('datalad.interface.unlock', 'Unlock', 'unlock'),
        ('datalad.interface.save', 'Save', 'save'),
        ('datalad.export', 'Export', 'export'),
    ])

_group_metadata = (
    'Commands for meta data handling',
    [
        ('datalad.metadata.search', 'Search',
         'search', 'search'),
        ('datalad.metadata.aggregate', 'AggregateMetaData',
         'aggregate-metadata', 'aggregate_metadata'),
    ])

_group_misc = (
    'Miscellaneous commands',
    [
        ('datalad.interface.test', 'Test'),
        ('datalad.interface.crawl', 'Crawl'),
        ('datalad.interface.crawl_init', 'CrawlInit', 'crawl-init'),
        ('datalad.interface.ls', 'Ls'),
        ('datalad.interface.clean', 'Clean'),
        ('datalad.interface.add_archive_content', 'AddArchiveContent',
         'add-archive-content'),
        ('datalad.interface.download_url', 'DownloadURL', 'download-url'),
    ])

_group_plumbing = (
    'Plumbing commands',
    [
        ('datalad.interface.annotate_paths', 'AnnotatePaths', 'annotate-paths'),
        ('datalad.distribution.clone', 'Clone'),
        ('datalad.distribution.create_test_dataset', 'CreateTestDataset',
         'create-test-dataset'),
        ('datalad.interface.diff', 'Diff', 'diff'),
        ('datalad.distribution.siblings', 'Siblings', 'siblings'),
        ('datalad.support.sshrun', 'SSHRun', 'sshrun'),
        ('datalad.distribution.subdatasets', 'Subdatasets', 'subdatasets'),
    ])
