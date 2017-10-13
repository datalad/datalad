# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

"""A pipeline for crawling BALSA datasets"""

import json
import os
import re

from shutil import rmtree
from os import curdir, makedirs, rmdir
from os.path import lexists, join as opj, abspath, exists, normpath
from collections import OrderedDict

# Import necessary nodes
from ..nodes.crawl_url import crawl_url
from ..nodes.matches import xpath_match, a_href_match
from ..nodes.misc import assign, skip_if, find_files, continue_if
from ..nodes.misc import debug
from ..nodes.misc import sub, switch
from ..nodes.annex import Annexificator
from ...consts import ARCHIVES_SPECIAL_REMOTE, DATALAD_SPECIAL_REMOTE
from ...utils import find_files as f_f, _path_
from ...utils import auto_repr
from ...utils import updated

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
    hardcodeNames = {'RVVG': '2016-Glasser_et_al-Multimodal_parcellation',
                     'W336': '2016-Donahue_et_al-Connection_strength_and_distance',
                     'WG33': '2016-VanEssen_et_al-BALSA',
                     'pkGn': '2016-Glasser_et_al-HCP_Neuroimaging_approach',
                     }

    annex = Annexificator(no_annex=True)
    lgr.info("Creating a BALSA collection pipeline")
    return [
        crawl_url(url),
        a_href_match('.*/study/show/(?P<dataset_id>.*)'),
        # skip the empty dataset used by BALSA for testing
        skip_if({'dataset_id': 'Jvw1'}, re=True),
        crawl_url(),
        xpath_match('substring(//*/h3/text(), 8, string-length(//*/h3/text()))', output='dataset'),
        # assign({'dataset_name': '%(dataset)s'}, interpolate=True),
        switch('dataset_id', {idkey: assign({'dataset_name': name}) for idkey, name in hardcodeNames.items()}),
        annex.initiate_dataset(
            template="balsa",
            data_fields=['dataset_id'],
            existing='skip'
        )
    ]


def extract_meta(data):
    content = [x['match'] for x in xpath_match('//*[@class="attributeLabel"]/..')(data)]
    content = [(re.sub('</li>', ', ', x)) for x in content]
    content = [(re.sub('<[^<]+?>|[\t|\n|\r]', '', (str(x.encode('ascii', 'ignore'))))).strip() for x in content]
    [content.remove(x) for x in content if x.find('SCENES:' or 'OWNERS:') >= 0]

    json_dict = OrderedDict(map(str, x.split(':', 1)) for x in content)

    if not exists(".datalad/meta"):
        makedirs(".datalad/meta")

    with open(_path_(".datalad/meta/balsa.json"), "w") as fi:
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
        con_files = set(f_f('.*', topdir=curdir, exclude='./(_files|.datalad)'))
        assert con_files

        # list of files that are individually downloaded
        files = set(f_f('.*', topdir='_files'))
        assert files

        for item_from_con in con_files:
            item_compare = normpath(opj('_files', item_from_con))
            if item_compare in files:
                key_item = self.repo.get_file_key(item_from_con)
                key_files_item = self.repo.get_file_key(item_compare)
                if key_item == key_files_item:
                    pass
                else:
                    lgr.warning("%s varies in content from the individually downloaded "
                                "file with the same name, it is removed and file "
                                "from canonical tarball is kept" % item_from_con)

                files.discard(item_compare)
            else:
                lgr.warning("%s does not exist in the individually listed files by name, "
                            "but will be kept from canonical tarball" % item_compare)

        if files:
            lgr.warning("The following files do not exist in the canonical tarball, but are "
                        "individually listed files and will not be kept: %s" % files)

        rmtree(files_path)
        yield data


def fix_the_filename(data):
    from datalad.utils import file_basename
    download_ext = file_basename(data['filename'], return_ext=True)[-1]
    orig_filename, orig_ext = file_basename(data['target_filename'], return_ext=True)  # data['filename_orig']
    if orig_ext != download_ext:
        assert(download_ext == 'zip')  # we are not aware of other cases
        assert(orig_ext == 'scene')
        data = data.copy()
        # They have a bug that the same name of the archive provided for multiple .scene files
        # available within the study
        data['filename'] = orig_filename + '_scene' + '.' + download_ext
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

    from datalad.downloaders.providers import Providers
    providers = Providers.from_config_files()
    balsa_downloader = providers.get_provider(url).get_downloader(url)

    def get_disposition_filename(data):
        yield updated(data, {'filename': balsa_downloader.get_status(data['url']).filename})

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
                    # TODO:  in case of .zip files we must not use checksum backends
                    #        since those are regenerated irreproducibly each time
                    #        so we should use URL backend with those
                    annex,
                ],
                [
                    a_href_match(files_url, min_count=2),
                    assign({'path': '_files/%(url_text)s'}, interpolate=True),
                    sub({'path': {' / ': '/'}}),
                    splitpath,
                    crawl_url(),
                    a_href_match('.*/download/.*', max_count=1),
                    # so we could use it in our magical function
                    # because get_disposition will override it
                    assign({'target_filename': '%(filename)s'}, interpolate=True),
                    get_disposition_filename,
                    fix_the_filename,
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
            annex.merge_branch('incoming-processed', commit=True, allow_unrelated=True),
            annex.finalize(tag=True),
        ],
        annex.switch_branch('master'),
        annex.finalize(cleanup=True),
    ]
