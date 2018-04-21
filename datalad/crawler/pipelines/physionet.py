# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""A pipeline for crawling a crcns dataset"""

# Import necessary nodes
import os
import re
from ..nodes.crawl_url import crawl_url
from ..nodes.crawl_url import parse_checksums
from ..nodes.matches import css_match, a_href_match, xpath_match
from ..nodes.misc import assign
from ..nodes.misc import debug
from ..nodes.misc import find_files
from ..nodes.misc import sub
from ..nodes.misc import skip_if, continue_if
from ..nodes.annex import Annexificator
from ...consts import DATALAD_SPECIAL_REMOTE, ARCHIVES_SPECIAL_REMOTE
from ...support.strings import get_replacement_dict

# Possibly instantiate a logger if you would like to log
# during pipeline creation
from logging import getLogger
from datalad.utils import updated

lgr = getLogger("datalad.crawler.pipelines.kaggle")

topurl = 'http://physionet.org'
physdburl = '%s/physiobank/database' % topurl


def parse_DBS(data):
    # do parsing... check the crcns.py use of parse_checksums
    response = data['response']
    for ds in [x.split('\t', 1)[0] for x in response.split('\n')]:
        if '/' in ds:
            # composite beast, so we might need to yeild super dataset first
            # and for some we might need to provide manual handling
            if ds not in {'gait-maturation-db/data'}:
                ds_up = '/'.join(ds.split('/')[:-1])
            else:
                ds_up = ds  # full name since it is worth it!
            if '/' in ds_up:
                # need to generate all supers first
                full_sds = []
                for sds in ds_up.split('/')[:-1]:
                    full_sds.append(sds)
                    yield updated(data, {'dataset': '/'.join(full_sds)})
            ds = ds_up  # yield this one instead
        yield updated(data, {'dataset': ds})


def superdataset_pipeline():
    lgr.info("Creating a PhysioNet collection pipeline")
    # Should return a list representing a pipeline
    annex = Annexificator(no_annex=True)
    return [
        crawl_url("%s/DBS" % physdburl),
        parse_DBS,
        assign({'dataset_name': '%(dataset)s'}, interpolate=True),
        annex.initiate_dataset(
            template="physionet",
            data_fields=['dataset'],
            # branch='incoming',  # there will be archives etc
            existing='skip',  # necessary since we create a hierarchy of those beasts
            # further any additional options
        )
    ]
#
#
# def extract_readme(data):
#     # TODO - extract data from the page/response  but not into README I guess since majority of datasets
#     # already provide README
#     if os.path.exists("README.txt"):
#         os.unlink("README.txt")
#     with open("README.txt", "w") as f:
#         f.write("CRCNS dataset from %(url)s" % data)
#     lgr.info("Generated README.txt")
#     yield {'filename': "README.txt"}
#

def pipeline(dataset,
             a_href_match_='.*',
             tarballs=False,
             datalad_downloader=False,
             use_current_dir=False,
             leading_dirs_depth=1,
             rename=None,
             backend='MD5E'):
    """Pipeline to crawl/annex a physionet dataset"""

    url = "%s/%s" % (physdburl, dataset)
    if not isinstance(leading_dirs_depth, int):
        leading_dirs_depth = int(leading_dirs_depth)

    lgr.info("Creating a pipeline to crawl data files from %s", url)
    special_remotes = []
    annex = Annexificator(
        create=False,  # must be already initialized etc
        backend=backend,
        statusdb='json',
        special_remotes=special_remotes,
        skip_problematic=True,
        options=["-c",
                 "annex.largefiles="
                 "exclude=README*"
                 " and exclude=LICENSE* and exclude=*.txt and exclude=*.json"
                 " and exclude=*.cfg"
                 " and exclude=*.edf.event"
                 " and exclude=DOI"
                 " and exclude=ANNOTATORS"
                 ]
    )

    def printnode(data):
        print(data['url'], data.get('path'), data.get('filename'), data.get('metadata'))
        yield data

    def write2metafile(data):
        metadata_path = '.datalad/meta.rfc822'
        # add homepage to all metadata files
        data['metadata']['Homepage'] = 'https://physionet.org'
        # add physionet dataset license
        data['metadata']['License'] = '''All data available from PhysioNet are free data. We are not aware of a de facto standard license for free data analogous to the GPL; your suggestions are welcome. 
        You may make and redistribute verbatim copies of data files.

        IMPORTANT: Modified copies of data files may not be distributed except terms mentioned at https://physionet.org/copying.shtml'''
        with open(metadata_path, "w") as f:
            f.write('\n'.join(
                ['{}: {}'.format(key, value) for key, value in data['metadata'].items()]
            ))
        lgr.info("Generated Metadata File")
        yield data

    def extract_html(data):
        def _html2txt(xpath_str, html, key):
            "extract, clean text from html using xpath selector"
            if key == 'Cite-As':  # join all matches if citation
                raw_html = ''.join(
                    [x['match'] for x in xpath_match(xpath_str)(html)][:2]
                )
            else:  # else get first match or empty string
                raw_html = next(xpath_match(xpath_str)(html), {'match': ''})['match']
            # remove html and escape sequences
            raw_html = re.sub('<[^<]+?>|[\t|\r]', '',
                              (str(raw_html.encode('ascii', 'ignore')))).strip()
            if key == 'DOI':  # remove 'doi' from text of doi key
                raw_html = re.sub('doi:', '', raw_html)
            # sub (possibly consecutive) newlines with single space
            return re.sub('\n ?\n|\n', ' ', raw_html)

        # extract metadata into dictionary from html using xpath selector string
        metadata = {mkey: _html2txt(xp_str, data, mkey) for mkey, xp_str in
                    (('DOI', '//aside/p/text()'),
                     ('Title', '//h1/text()'),
                     ('Ack', '//p[preceding-sibling::h2[contains(text(), "Acknowledgments")]]'),
                     ('Cite-As', '//*[@class="reference"]'),
                     ('Notice', '//*[@class="notice"]'),)}

        # merge acknowledgment, notice into description
        metadata['Description'] = 'Notice\n' + metadata['Notice'] + '\nAcknowledgments\n' + metadata['Ack']
        del metadata['Ack']
        del metadata['Notice']
        # extract shortname of dataset
        metadata['Name'] = str(data['url'].split('/')[-2]).encode('ascii', 'ignore')
        yield updated(data, {'metadata': metadata})


    crawler = crawl_url(
        url,
        matchers=[
            a_href_match('%s.*/[^.].*/$' % url)
            #a_href_match('%s.*/S001.*/$' % url)
        ]
    )

    return [  # Download all the archives found on the project page
        [
            crawler,
            extract_html,
            #printnode,
            write2metafile,
            a_href_match(url +'(/(?P<path>.*))?/[^/]*$'), #, min_count=1),
            # skip those which have # or ? in last component
            continue_if({'url': url.rstrip('/') + '(/.*)?/[^#?/][^/]*$'}, re=True),
            annex,
        ],
        annex.finalize(cleanup=True)
    ]

    if rename:
        urls_pipe += [sub({'filename': get_replacement_dict(rename)})]

    return [
        annex.switch_branch('incoming'),
        [
            urls_pipe + [
                annex,
            ],
        ],
        annex.switch_branch('incoming-processed'),
        [   # nested pipeline so we could skip it entirely if nothing new to be merged
            annex.merge_branch('incoming', strategy='theirs', commit=False),  #, skip_no_changes=False),
            [   # Pipeline to augment content of the incoming and commit it to master
                find_files("\.(zip|tgz|tar(\..+)?)$", fail_if_none=tarballs),  # So we fail if none found -- there must be some! ;)),
                annex.add_archive_content(
                    existing='archive-suffix',
                    # Since inconsistent and seems in many cases no leading dirs to strip, keep them as provided
                    strip_leading_dirs=bool(leading_dirs_depth),
                    delete=True,
                    leading_dirs_depth=leading_dirs_depth,
                    use_current_dir=use_current_dir,
                    rename=rename,
                    exclude='.*__MACOSX.*',  # some junk penetrates
                ),
            ],
        ],
        annex.switch_branch('master'),
        annex.merge_branch('incoming-processed', allow_unrelated=True),
        annex.finalize(cleanup=True),
    ]
