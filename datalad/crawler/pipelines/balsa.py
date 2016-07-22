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
from os.path import lexists

# Import necessary nodes
from ..nodes.crawl_url import crawl_url
from ..nodes.matches import xpath_match, a_href_match
from ..nodes.misc import assign
from ..nodes.misc import Sink
from ..nodes.misc import find_files
from ..nodes.annex import Annexificator
from ...consts import ARCHIVES_SPECIAL_REMOTE

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


class extract_info(object):

    def __init__(self, dataset):
        """
        Node to exract information from dataset link

        Parameters
        ----------
        dataset: str
            Id of the BASLA dataset (e.g. W336)
        """
        self.dataset = dataset

    def __call__(self, data):

        data['title'] = xpath_match('//*/p[1]|span/text()')(data)
        data['species'] = xpath_match('//*/p[2]|span/text()')(data)
        data['description'] = xpath_match('//*/p[3]|span/text()')(data)
        data['publication'] = xpath_match('//*/p[4]|span/text()')(data)
        data['full tarball'] = xpath_match('//*[@class="btn-group"]/a[contains(text(), "d")]')(data)
        return data

#
# class compare(object):
#
#     def __init__(self, ):
#         """
#         Node to exract information from dataset link
#
#         Parameters
#         ----------
#         dataset: str
#             Id of the BASLA dataset (e.g. W336)
#         """
#
#     def __call__(self):




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

    # all files to be sunk = xpath_match('//*[@class="modal-body"]//a/text()')

    # BALSA has versioning, but no clear versions to releases of the studies
    return [
        annex.switch_branch('incoming'),
        [
            crawl_url(TOPURL),
            [
                assign({'dataset': dataset}),
                extract_info(dataset),
                [  # README
                    extract_readme,
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

            # verify files node, takes annex path as input, will have to remove a set of files


            # assign({'path': '_file/%(path)s'}, interpolate=True),

            annex.switch_branch('master'),
            annex.merge_branch('incoming-processed', commit=True),
            annex.finalize(tag=True),
        ],
        annex.switch_branch('master'),
        annex.finalize(cleanup=True),
    ]
