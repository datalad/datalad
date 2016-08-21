# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

"""A pipeline for crawling BALSA datasets"""

import os
from shutil import rmtree
from os import curdir, makedirs, rmdir
from os.path import lexists, join as opj, abspath, exists, normpath
from string import split
from collections import OrderedDict

# Import necessary nodes
from ..nodes.crawl_url import crawl_url
from ..nodes.matches import xpath_match, a_href_match
from ..nodes.misc import assign, skip_if, find_files, continue_if
from ..nodes.misc import debug
from ..nodes.misc import sub
from ..nodes.annex import Annexificator
from ...consts import ARCHIVES_SPECIAL_REMOTE, DATALAD_SPECIAL_REMOTE
from datalad.utils import find_files as f_f
from datalad.support.annexrepo import *
from datalad.support.gitrepo import *

from logging import getLogger
lgr = getLogger("datalad.crawler.pipelines.balsa")

TOPURL = "https://balsa.wustl.edu/"


def superdataset_pipeline(url=TOPURL):
    """
    Parameters
    ----------
    url: str
       URL point to all datasets, hence the URL at the top

    """
    url = opj(url, 'study/')

    annex = Annexificator()
    lgr.info("Creating a BALSA collection pipeline")
    return [
        crawl_url(url),
        a_href_match('.*/study/show/(?P<dataset_id>.*)'),
        # skip the empty dataset used by BALSA for testing
        skip_if({'dataset_id': 'Jvw1'}, re=True),
        crawl_url(),
        xpath_match('substring(//*/h3/text(), 8, string-length(//*/h3/text()))', output='dataset'),
        assign({'dataset_name': '%(dataset)s'}, interpolate=True),
        # [
        #     continue_if({'dataset_id': 'RVVG'}),
        #     assign({'dataset_name': '%(dataset_id)s: 2016-Glasser_et_al-Multimodal_parcellation'}, interpolate=True),
        # ],
        # [
        #     continue_if({'dataset_id': 'W336'}),
        #     assign({'dataset_name': '%(dataset_id)s: 2016-Donahue_et_al-Connection_strength_and_distance'}, interpolate=True),
        # ],
        # [
        #     continue_if({'dataset_id': 'WG33'}),
        #     assign({'dataset_name': '%(dataset_id)s: 2016-VanEssen_et_al-BALSA'}, interpolate=True),
        # ],
        annex.initiate_dataset(
            template="balsa",
            data_fields=['dataset_id'],
            existing='skip'
        )
    ]


def extract_meta(data):

    content = [x['match'] for x in xpath_match('//*[@class="attributeLabel"]/../p')(data)]
    content = [(re.sub('<[^<]+?>|[\t|\n]', '', (str(x.encode('ascii', 'replace'))))).strip() for x in content]

    json_dict = OrderedDict(map(str, x.split(':', 1)) for x in content)

    content2 = [x['match'] for x in xpath_match('//*[@class="attributeLabel"]/../div/ul/..')(data)]
    content2 = [(re.sub('</li>', ', ', x)) for x in content2]
    content2 = [(re.sub('<[^<]+?>|[\t|\n]', '', (str(x.encode('ascii', 'replace'))))).strip() for x in content2]

    dict2 = OrderedDict(map(str, x.split(':', 1)) for x in content2)
    json_dict.update({key: dict2[key] for key in dict2 if key not in ['SCENES', 'OWNERS']})

    if not exists(".datalad/meta"):
        makedirs(".datalad/meta")

    opj(".datalad/meta/balsa.json".split('/'))
    with open(".datalad/meta/balsa.json", "w") as fi:
        json.dump(json_dict, fi, indent=1)
        lgr.info("Generated descriptor file")
        yield {'filename': ".datalad/meta/balsa.json"}


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

    def verify_files(self, data):
        files_path = opj(abspath(curdir), '_files')

        # list of files that exist from canonical tarball
        con_files = list(f_f('.*', topdir=curdir, exclude='./(_files|.datalad)'))

        # list of file that are individually downloaded
        files = list(f_f('.*', topdir='_files'))
        files_key = [self.repo.get_file_key(item) for item in files]

        for item in con_files:
            item = normpath(opj('_files', item))
            if item in files:
                key_item = self.repo.get_file_key(opj('./', item))
                if key_item in files_key:
                    pass
                else:
                    lgr.warning("%s is varies in content from the individually downloaded "
                                "files, is removed and file from canonical tarball is kept" % item)
                self.repo.remove(item)
                files = list(f_f('.*', topdir='_files'))
            else:
                lgr.warning("%s does not exist in the individaully listed files by name, "
                            "but will be kept from canconical tarball" % item)
        if files:
            lgr.warning("The following files do not exist in the canonical tarball, but are "
                        "individually listed files and will not be kept: %s" % files)
            rmtree(files_path)

        yield data


def pipeline(dataset_id, url=TOPURL):
    lgr.info("Creating a pipeline for the BALSA dataset %s" % dataset_id)
    annex = Annexificator(create=False,
                          statusdb='json',
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

    if not exists("_files"):
        makedirs("_files")

    def splitpath(data):
        data = data.copy()
        fullpath = data.pop('path')
        path = os.path.dirname(fullpath)
        if path:
            data['path'] = path
        data['filename'] = os.path.basename(fullpath)
        yield data

    files_url = opj(url, 'file/show/')  # files_url = https://balsa.wustl.edu/file/show/

    url = opj(url, 'study/')  # url = https://balsa.wustl.edu/study/
    dataset_url = '%sshow/%s' % (url, dataset_id)  # url = https://balsa.wustl.edu/study/show/[dataset_id]

    balsa = BalsaSupport(repo=annex.repo)

    # BALSA has no versioning atm, so no changelog either
    return [
        annex.switch_branch('incoming'),
        [
            crawl_url(url),
            [
                assign({'dataset': dataset_id}),
                skip_if({'dataset': 'test study upload'}, re=True),
            ],
            [
                crawl_url(dataset_url),
                [
                    extract_meta,
                    annex,
                ],
                [
                    # canonical tarball
                    a_href_match('.*/download/.*', min_count=1),
                    annex,
                ],
                [
                    a_href_match(files_url, min_count=2),
                    assign({'path': '_files/%(url_text)s'}, interpolate=True),
                    sub({'path': {' / ': '/'}}),
                    splitpath,
                    annex,
                ],
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
            balsa.verify_files,
            annex.switch_branch('master'),
            annex.merge_branch('incoming-processed', commit=True),
            annex.finalize(tag=True),
        ],
        annex.switch_branch('master'),
        annex.finalize(cleanup=True),
    ]
