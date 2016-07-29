# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

"""A pipeline for crawling BALSA datasets"""

import os, re
from os import curdir, listdir
from os.path import lexists, join as opj

# Import necessary nodes
from ..nodes.crawl_url import crawl_url
from ..nodes.matches import xpath_match, a_href_match
from ..nodes.misc import assign, skip_if
from ..nodes.misc import find_files
from ..nodes.annex import Annexificator
from ...consts import ARCHIVES_SPECIAL_REMOTE, DATALAD_SPECIAL_REMOTE
from datalad.support.annexrepo import *
from datalad.support.gitrepo import *

from logging import getLogger
lgr = getLogger("datalad.crawler.pipelines.balsa")

TOPURL = "https://balsa.wustl.edu/study"


def superdataset_pipeline(url=TOPURL):
    """
    Parameters
    ----------
    url: str
       URL point to all datasets, hence the URL at the top

    """
    # xpath_match('//*/tr/td[1]/a/text()', output='dataset') # dataset = Connection Strength and Distance with Tractography
    # xpath_match('//*/tr/td[1]/a/@href', output='dataset_id')  # dataset_id = /study/show/W336

    annex = Annexificator()
    lgr.info("Creating a BALSA collection pipeline")
    return [
        crawl_url(url),
        a_href_match('.*/study/show/(?P<dataset_id>.*)'),
        # skip the empty dataset used by BALSA for testing
        skip_if({'dataset_id': 'Jvw1'}, re=True),
        crawl_url(),
        xpath_match('//*/h3/text()', output='dataset'),
        assign({'dataset_name': '%(dataset)s'}, interpolate=True),
        annex.initiate_dataset(
            template="balsa",
            data_fields=['dataset_id', 'dataset'],
            existing='skip'
        )
    ]


# def extract_readme(data):
#
#     data['full title'] = xpath_match('//*/p[1]|span/text()')(data)
#     data['species'] = xpath_match('//*/p[2]|span/text()')(data)
#     data['description'] = xpath_match('//*/p[3]|span/text()')(data)
#     data['publication'] = xpath_match('//*/p[4]|span/text()')(data)
#     data['full tarball'] = xpath_match('//*[@class="btn-group"]/a[contains(text(), "d")]')(data)
#
#     if lexists("README.txt"):
#         os.unlink("README.txt")
#
#     with open("README.txt", "w") as fi:
#         fi.write("""\
# BALSA sub-dataset %(dataset)s
# ------------------------
#
# Full Title: %(title)s
# Species: %(species)s
#         """ % data)
#
#         lgr.info("Generated README.txt")
#         yield {'filename': "README.txt"}


@auto_repr
class BalsaSupport(object):

    def __init__(self, repo):
        """Verifies that the canoncial tarball contains all files that are
        individually listed

           Parameters
           ----------
           repo: str
             annex repo to which dataset is being annexed
           """
        self.repo = repo

    def verify_files(self):

        files_path = opj(curdir, '_files')

        con_files = listdir(curdir)  # list of files that exist from canonical tarball
        files = listdir(files_path)  # list of file that are individually downloaded
        files_key = [self.repo.get_file_key(item) for item in files]

        for item in con_files:
            if item in files:
                key = self.repo.get_file_key(item)
                if key in files_key:
                    pass
                else:
                    lgr.warning("%s is varies in content from the individually downloaded "
                                "files, is removed and file from canonical tarball is kept" % item)
                p = opj(files_path, item)
                self.repo.remove(p)
            else:
                lgr.warning("%s does not exist in the individaully listed files by name, "
                            "but will be kept from canconical tarball" % item)
        if files:
            lgr.warning("The following files do not exist in the canonical tarball, but are "
                        "individaully listed files and will not be kept" % files)


def pipeline(dataset_id):
    lgr.info("Creating a pipeline for the BALSA dataset %s" % dataset_id)
    annex = Annexificator(create=False, statusdb='json', allow_dirty=True,
                          special_remotes=[ARCHIVES_SPECIAL_REMOTE, DATALAD_SPECIAL_REMOTE],
                          options=["-c",
                                   "annex.largefiles="
                                   "exclude=Makefile and exclude=LICENSE* and exclude=ISSUES*"
                                   " and exclude=CHANGES* and exclude=README*"
                                   " and exclude=*.[mc] and exclude=dataset*.json"
                                   " and exclude=*.txt"
                                   " and exclude=*.json"
                                   " and exclude=*.tsv"
                                   ])

    dataset_url = '%s%s' % (TOPURL, dataset_id)
    balsa = BalsaSupport(repo=annex.repo)
    # BALSA has no versioning atm, so no changelog either

    return [
        annex.switch_branch('incoming'),
        [
            crawl_url(TOPURL),
            [
                assign({'dataset': dataset_id}),
                skip_if({'dataset': 'test study upload'}, re=True),
                # canonical tarball
                a_href_match('https://balsa.wustl.edu/study/download/', min_count=1),
                annex,
            ],
            [
                crawl_url(dataset_url),
                a_href_match('https://balsa.wustl.edu/study/show'),
                assign({'path': '_files/%(path)s'}, interpolate=True),
                annex,
            ],

        ],
        annex.remove_obsolete(),
        [
            annex.switch_branch('incoming-processed'),
            annex.merge_branch('incoming', one_commit_at_a_time=True, strategy='theirs', commit=False),
            [
               {'loop': True},
               find_files("\.(zip|tgz|tar(\..+)?)$", fail_if_none=True),
               annex.add_archive_content(
                   existing='archive-suffix',
                   strip_leading_dirs=True,
                   leading_dirs_depth=1,
                   delete=True,
                   exclude=['(^|%s)\._' % os.path.sep],
               ),
            ],
            verify_files(balsa),
            annex.switch_branch('master'),
            annex.merge_branch('incoming-processed', commit=True),
            annex.finalize(tag=True),
        ],
        annex.switch_branch('master'),
        annex.finalize(cleanup=True),
    ]
