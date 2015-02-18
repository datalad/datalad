"""
This layer makes the difference between an arbitrary annex and a datalad-managed dataset.
"""
__author__ = 'Benjamin Poldrack'

import os

from annexrepo import AnnexRepo

class Dataset(AnnexRepo):
    """
    Representation of an dataset handled by datalad.
    Implementations of datalad commands are supposed to use this rather than AnnexRepo or GitRepo directly,
    since any restrictions on annexes required by datalad due to its cross-platform distribution approach are handled here.
    Also an AnnexRepo has no idea of any datalad configuration need, of course.
    """

    def __init__(self, path, url=None):
        """
        Creates a dataset representation by path. If an url to a git repo is given, it will be cloned.
        :param destination: path to git annex repository
        :param url: valid git url ( http://www.kernel.org/pub/software/scm/git/docs/git-clone.html#URLS ) to clone from
        :return:
        """

        #super(self.__class__, self).__init__(path, url)
        super(Dataset, self).__init__(path, url)

        # TODO: create proper .datalad-file for marking as dataset and future use for config
        os.chdir(self.path)
        dataladFile = open('.datalad','w')
        dataladFile.write('dummy')
        dataladFile.close()


    def dummy_dataset_command(self):
        """

        :return:
        """
        raise NotImplementedError
