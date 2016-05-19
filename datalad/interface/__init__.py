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


# the following should be series of import definitions for interface implementations
# that shall be exposed in the Python API and the cmdline interface
# all interfaces should be associated with (at least) one of the groups below
_group_dataset = (
    'Commands for dataset operations',
    [
        # source module, source object[, dest. cmdline name[, dest python name]]
        # src module can be relative, but has to be relative to the main 'datalad' package
        ('datalad.distribution.install', 'Install'),
        ('datalad.distribution.publish', 'Publish'),
        ('datalad.distribution.uninstall', 'Uninstall'),
        ('datalad.distribution.move', 'Move'),
        ('datalad.distribution.update', 'Update'),
        ('datalad.distribution.create_publication_target_sshwebserver',
         'CreatePublicationTargetSSHWebserver',
         'create-publication-target-sshwebserver'),
        ('datalad.distribution.add_sibling', 'AddSibling', 'add-sibling'),
        ('datalad.distribution.modify_subhandle_urls', 'ModifySubhandleURLs',
         'modify-subhandle-urls'),
    ])

_group_misc = (
    'Miscellaneous commands',
    [
        ('datalad.interface.test', 'Test'),
        ('datalad.interface.crawl', 'Crawl'),
        ('datalad.interface.pull', 'Pull'),
        ('datalad.interface.push', 'Push'),
        ('datalad.interface.ls', 'Ls'),
        ('datalad.interface.clean', 'Clean'),
        ('datalad.interface.add_archive_content', 'AddArchiveContent',
         'add-archive-content'),
        ('datalad.interface.download_url', 'DownloadURL', 'download-url'),
        # very optional ones
        ('datalad.distribution.tests.create_test_dataset', 'CreateTestDataset',
         'create-test-dataset'),
    ])
