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
from os.path import lexists

# Import necessary nodes
from ..nodes.crawl_url import crawl_url
from ..nodes.matches import xpath_match, a_href_match
from ..nodes.misc import assign
from ..nodes.misc import find_files
from ..nodes.annex import Annexificator
from ...consts import ARCHIVES_SPECIAL_REMOTE
from datalad.support.annexrepo import *
from datalad.support.gitrepo import *

from logging import getLogger
lgr = getLogger("datalad.crawler.pipelines.balsa")

TOPURL = "http://balsa.wustl.edu"


# TODO unknown yet how to access dataset links from TOPURL
# def superdataset_pipeline(url=TOPURL):
#     """
#     Parameters
#     ----------
#     url: str
#        URL point to all datasets, hence the URL at the top
#     -------
#
#     """
#     annex = Annexificator()
#     lgr.info("Creating a BALSA collection pipeline")
#     return [
#         crawl_url(url),
#         xpath_match('<xpath selectors to dataset link here>', output='dataset'),
#         # http://balsa.wustl.edu/study/show<dataset ID here>
#         assign({'dataset_name': '%(dataset)s'}, interpolate=True),
#         annex.initiate_dataset(
#             template="balsa",
#             data_fields=['dataset'],
#             existing='skip'
#         )
#     ]


def extract_readme(data):

    data['title'] = xpath_match('//*/p[1]|span/text()')(data)
    data['species'] = xpath_match('//*/p[2]|span/text()')(data)
    data['description'] = xpath_match('//*/p[3]|span/text()')(data)
    data['publication'] = xpath_match('//*/p[4]|span/text()')(data)
    data['full tarball'] = xpath_match('//*[@class="btn-group"]/a[contains(text(), "d")]')(data)

    if lexists("README.txt"):
        os.unlink("README.txt")

    with open("README.txt", "w") as fi:
        fi.write("""\
BALSA sub-dataset %(dataset)s
------------------------

Full Title: %(title)s
Species: %(species)s
        """ % data)

        lgr.info("Generated README.txt")
        yield {'filename': "README.txt"}


def verify_files():

    files_path = path + '/_files'

    con_files = listdir(path)
    files = listdir(files_path)

    # all files individually downloaded that do not exists in canonical tarball
    list1 = [item for item in files if item not in con_files]
    if list1:
            lgr.warning("%s do(es) not exist in the canonical tarball by name" % list1)
    # list1_keys = [get_file_key(item) for item in files]

    # all files from canonical tarball that were not from the batch individually downloaded
    list2 = [item for item in con_files if item not in files]
    if list2:
        lgr.warning("%s do(es) not exist in the individaully listed files by name" % list2)
    # list2_keys = [get_file_key(item) for item in con_files]

    if not list1 and not list2:
        remove(files)  # GitRepo ?
        lgr.info("Removing individually listed files due to no discrepancies found with canonical tarball")

    if not list1 and list2:
        remove(files)  # GitRepo ?
        lgr.info("Removing individually listed files due as canonical tarball contains them and more")

    if list1 and not list2:
        remove(con_files)  # GitRepo ?
        # move those in _files into annexrepo, delete _files path
        lgr.info("Removing extracted files from canonical tarball and replacing them with individually "
                 "downloaded files due to discrepancies")

# files that are meant to be individually downloaded = xpath_match('//*[@class="modal-body"]//a/text()')


def pipeline(dataset):
    lgr.info("Creating a pipeline for the BALSA dataset %s" % dataset)
    annex = Annexificator(create=False, statusdb='json', special_remotes=[ARCHIVES_SPECIAL_REMOTE],
                          options=["-c",
                                   "annex.largefiles="
                                   "exclude=Makefile and exclude=LICENSE* and exclude=ISSUES*"
                                   " and exclude=CHANGES* and exclude=README*"
                                   " and exclude=*.[mc] and exclude=dataset*.json"
                                   " and exclude=*.txt"
                                   " and exclude=*.json"
                                   " and exclude=*.tsv"
                                   ])

    # BALSA has versioning of scene files only
    # TODO: changelog for scene files
    return [
        annex.switch_branch('incoming'),
        [
            crawl_url(TOPURL),
            [
                assign({'dataset': dataset}),
                [  # README
                    extract_readme,
                    annex,
                ],
                [
                    assign({'path': '_files/%(path)s'}, interpolate=True),
                    annex,
                ],
                # canonical tarball
                a_href_match('http://balsa.wustl.edu/study/download/', min_count=1),
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
            verify_files(curdir+'/annex'),  # should this be placed here, however?
            annex.switch_branch('master'),
            annex.merge_branch('incoming-processed', commit=True),
            annex.finalize(tag=True),
        ],
        annex.switch_branch('master'),
        annex.finalize(cleanup=True),
    ]
