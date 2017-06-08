# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""A pipeline for crawling XNAT servers/datasets (e.g. NITRC/ir)"""

"""
Notes:

- xml entries for subject contain meta-data
- in longitudinal studies there could be multiple ages for a subject... find where
  it is

    1  curl -I ftp://www.nitrc.org/fcon_1000/htdocs/AnnArbor_a.tar
    2  man wget
    3  wget
    4  curl http://www.nitrc.org/ir/data/projects/cs_schizbull08
    5  curl http://www.nitrc.org/ir/data/projects/fcon_1000/subjects
    6  curl http://www.nitrc.org/ir/data/projects/fcon_1000/subjects?format=csv
    7  curl http://www.nitrc.org/ir/data/projects/fcon_1000/subjects/Taipei_sub43181?format=xml
    8* curl http://www.nitrc.org/ir/data/projects/fcon_1000/subjects/Taipei_sub431
    9  curl http://www.nitrc.org/ir/data/projects/fcon_1000/subjects?format=csv
   10  curl http://www.nitrc.org/ir/data/projects/fcon_1000/subjects
   11  curl http://www.nitrc.org/ir/data/projects/fcon_1000/subjects/SaintLouis_sub82830/experiments
   12  curl http://www.nitrc.org/ir/data/projects/fcon_1000/subjects/SaintLouis_sub82830/experiment/SaintLouis_sub82830/scans
   13* curl http://www.nitrc.org/ir/data/projects/fcon_1000/subjects/SaintLouis_sub82830/experiments?
   14  curl http://www.nitrc.org/ir/data/projects/fcon_1000/subjects/SaintLouis_sub82830/experiment/SaintLouis_sub82830
   15  curl http://www.nitrc.org/ir/data/projects/fcon_1000/subjects/SaintLouis_sub82830/experiment/SaintLouis_sub82830?format=csv
   16  curl http://www.nitrc.org/ir/data/projects/fcon_1000/subjects/SaintLouis_sub82830/experiment/SaintLouis_sub82830?format=xml
   17  curl http://www.nitrc.org/ir/data/projects/fcon_1000/subjects/SaintLouis_sub82830/experiment/SaintLouis_sub82830/scan/SaintLouis_sub82830_func_rest.nii.gz
   18  curl http://www.nitrc.org/ir/data/projects/fcon_1000/subjects/SaintLouis_sub82830/experiment/SaintLouis_sub82830/scan/SaintLouis_sub82830_func_rest.nii.gz/resources
   19  curl http://www.nitrc.org/ir/data/projects/fcon_1000/subjects/SaintLouis_sub82830/experiment/SaintLouis_sub82830/scan/SaintLouis_sub82830_func_rest.nii.gz/resources?format=csv
   20  curl http://www.nitrc.org/ir/data/projects/fcon_1000/subjects/SaintLouis_sub82830/experiments/SaintLouis_sub82830/scan/SaintLouis_sub82830_func_rest.nii.gz/resources?format=csv
   21  curl http://www.nitrc.org/ir/data/projects/fcon_1000/subjects/SaintLouis_sub82830/experiments/SaintLouis_sub82830/scans
   22  curl http://www.nitrc.org/ir/data/projects/fcon_1000/subjects/SaintLouis_sub82830/experiments/SaintLouis_sub82830/scans/anat_mprage_anonymized/resources
   23  curl http://www.nitrc.org/ir/data/projects/fcon_1000/subjects/SaintLouis_sub82830/experiments/SaintLouis_sub82830/scans/anat_mprage_anonymized/resources/BRIK/files
   24  curl -O http://www.nitrc.org/ir/data/projects/fcon_1000/subjects/SaintLouis_sub82830/experiments/SaintLouis_sub82830/scans/anat_mprage_anonymized/resources/BRIK/files/scan_mprage_anonymized.nii.gz

   28  curl -I http://www.nitrc.org/ir/data/projects/fcon_1000/subjects/SaintLouis_sub82830/experiments/SaintLouis_sub82830/scans/anat_mprage_anonymized/resources/BRIK/files/scan_mprage_anonymized.nii.gz
   29  curl http://www.nitrc.org/ir/data/projects/fcon_1000/subjects/SaintLouis_sub82830/experiments/SaintLouis_sub82830/scans/anat_mprage_anonymized/resources/BRIK/files?format=csv
   30  curl http://www.nitrc.org/ir/data/projects
   31  curl http://www.nitrc.org/ir/data/projects?format=csv
   32  curl http://www.nitrc.org/ir/data/projects/cs_schizbull08/subjects
   33  curl http://www.nitrc.org/ir/data/projects/cs_schizbull08/subjects | format_json
   34  curl http://www.nitrc.org/ir/data/projects/cs_schizbull08/subjects/BPDwoPsy_054/experiments | format_json
   35  curl http://www.nitrc.org/ir/data/projects/cs_schizbull08/subjects/BPDwoPsy_054/experiments/BPDwoPsy_054_MR/scans
   36  curl http://www.nitrc.org/ir/data/projects/cs_schizbull08/subjects/BPDwoPsy_054/experiments/BPDwoPsy_054_MR/scans |format_json
   37  curl http://www.nitrc.org/ir/data/projects/cs_schizbull08/subjects/BPDwoPsy_054/experiments/BPDwoPsy_054_MR/assessors
   38  curl http://www.nitrc.org/ir/data/projects/cs_schizbull08/subjects/BPDwoPsy_054/experiments/BPDwoPsy_054_MR/assessors
   39  curl http://www.nitrc.org/ir/data/projects/cs_schizbull08/subjects/BPDwoPsy_054/experiments/BPDwoPsy_054_MR/assessors/BPDwoPsy_054_MR_seg
   40  curl http://www.nitrc.org/ir/data/projects/cs_schizbull08/subjects/BPDwoPsy_054/experiments/BPDwoPsy_054_MR/assessors/BPDwoPsy_054_MR_seg?format=xml
   41  curl http://www.nitrc.org/ir/data/projects/cs_schizbull08/subjects/BPDwoPsy_054/experiments/BPDwoPsy_054_MR/assessors/BPDwoPsy_054_MR_seg/resources
   42  curl http://www.nitrc.org/ir/data/projects/cs_schizbull08/subjects/BPDwoPsy_054/experiments/BPDwoPsy_054_MR/assessors/BPDwoPsy_054_MR_seg/resources/NIfTI/files
   43  curl -O http://www.nitrc.org/ir/data/projects/cs_schizbull08/subjects/BPDwoPsy_054/experiments/BPDwoPsy_054_MR/assessors/BPDwoPsy_054_MR_seg/resources/NIfTI/files/seg.nii.gz
   44  fslview seg.nii.gz
   45  curl -u user:pass http://www.nitrc.org/ir/data/JSESSION
   46  history
   47  curl http://www.nitrc.org/ir/data/projects?format=csv
"""

import os
import re
import json
from os.path import lexists

# Import necessary nodes
from ..nodes.crawl_url import crawl_url
from ..nodes.matches import css_match, a_href_match
from ..nodes.misc import assign
from ..nodes.misc import sub
from ..nodes.misc import switch
from ..nodes.misc import func_to_node
from ..nodes.misc import find_files
from ..nodes.misc import skip_if
from ..nodes.misc import debug
from ..nodes.misc import fix_permissions
from ..nodes.annex import Annexificator
from ...support.s3 import get_versioned_url
from ...utils import updated
from ...consts import ARCHIVES_SPECIAL_REMOTE, DATALAD_SPECIAL_REMOTE
from datalad.downloaders.providers import Providers

# For S3 crawling
from ..nodes.s3 import crawl_s3
from .openfmri_s3 import pipeline as s3_pipeline
from datalad.api import ls
from datalad.dochelpers import exc_str

# Possibly instantiate a logger if you would like to log
# during pipeline creation
from logging import getLogger
lgr = getLogger("datalad.crawler.pipelines.openfmri")

from datalad.tests.utils import eq_


def list_to_dict(l, field):
    return {r.pop(field): r for r in l}

class XNATServer(object):
    def __init__(self, topurl):
        self.topurl = topurl
        from datalad.downloaders.providers import Providers
        providers = Providers.from_config_files()
        self.downloader = providers.get_provider(topurl).get_downloader(topurl)

    def __call__(self, query, format='json', fields_to_check={'totalRecords', 'Result'}):
        query_url = "%s/%s" % (self.topurl, query)
        if format:
            query_url += "?format=%s" % format
        out = self.downloader.fetch(query_url)
        if format == 'json':
            j = json.loads(out)
            assert j.keys() == ['ResultSet']
            j = j['ResultSet']
            if fields_to_check:
                eq_(set(j.keys()), fields_to_check)
            return j['Result']
        return out

    def get_projects(self):
        return list_to_dict(self('data/projects'), 'ID')

    def get_subjects(self, project):
        return list_to_dict(
            self('data/projects/%(project)s/subjects' % locals()),
            'ID'
        )

    def get_experiments(self, project, subject):
        return list_to_dict(
            # http://www.nitrc.org/ir/data/projects/fcon_1000/subjects/SaintLouis_sub82830/experiments?
            self('data/projects/%(project)s/subjects/%(subject)s/experiments' % locals()),
            'ID'
        )

    def get_files(self, project, subject, experiment):
        files = []
        for rec_type in ('scans', 'assessors'):
            url = 'data/projects/%(project)s/subjects/%(subject)s/experiments/%(experiment)s/%(rec_type)s' % \
                      locals()
            recs = self(url)
            files_ = []
            for rec in recs:
                files_.extend(self(url + '/%(ID)s/files' % rec, fields_to_check={'title', 'Result', 'Columns'}))
            for f in files_:
                f['rec_type'] = rec_type
            files.extend(files_)
        return files

    def get_all_files_for_project(self, project, subjects=None, experiments=None):
        for subject in (subjects or self.get_subjects(project)):
            for experiment in (experiments or self.get_experiments(project, subject)):
                for file_ in self.get_files(project, subject, experiment):
                    yield file_