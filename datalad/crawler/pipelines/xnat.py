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
from datalad.utils import assure_list


def list_to_dict(l, field):
    return {r.pop(field): r for r in l}

DEFAULT_RESULT_FIELDS = {'totalrecords', 'result'}
PROJECT_ACCESS_TYPES = {'public', 'protected', 'private'}


def lower_case_the_keys(d):
    """Create a dict with keys being lower cased but with a check against collisions
    
    If d is a list of tuple, would recurse into its elements
    """
    if not isinstance(d, dict):
        assert isinstance(d, (list, tuple))
        return d.__class__(
            lower_case_the_keys(x) for x in d
        )
    out = {}
    for k, v in d.items():
        kl = k.lower()
        if kl in out:
            raise ValueError(
                "We already got key %s=%r, but trying to add =%r"
                % (kl, out[kl], v)
            )
        out[kl] = v
    return out


class XNATServer(object):
    def __init__(self, topurl):
        self.topurl = topurl
        from datalad.downloaders.providers import Providers
        providers = Providers.from_config_files()
        self.downloader = providers.get_provider(topurl).get_downloader(topurl)

    def __call__(self, query,
                 format='json',
                 options=None,
                 fields_to_check=DEFAULT_RESULT_FIELDS):
        query_url = "%s/%s" % (self.topurl, query)
        options = options or {}
        if format:
            options['format'] = format
        if options:
            # TODO: use the helper we have
            query_url += "?" + '&'.join(("%s=%s" % (o, v) for o, v in options.items()))
        out = self.downloader.fetch(query_url)
        if format == 'json':
            j = json.loads(out)
            j = lower_case_the_keys(j)
            assert j.keys() == ['resultset']
            j = lower_case_the_keys(j['resultset'])
            if fields_to_check:
                eq_(set(j.keys()), fields_to_check)
            return lower_case_the_keys(j['result'])
        return out

    def get_projects(self, limit=None):
        """Get list of projects 
        
        Parameters
        ----------
        limit: {'public', 'protected', 'private', None} or list of thereoff
           'private' -- projects you have no any access to. 'protected' -- you could
           fetch description but not the data. None - would list all the projects
        """
        # accessible  option could limit to the projects I have access to
        kw = {}
        if limit:
            kw['options'] = {"accessible": "true"} if limit else None
            kw['fields_to_check'] = DEFAULT_RESULT_FIELDS | {'title', 'xdat_user_id'}
        out = list_to_dict(self('data/projects', **kw), 'id')
        if limit:
            limit = assure_list(limit)
            # double check that all the project_access thingies in the set which
            # we know
            assert all(p['project_access'] in PROJECT_ACCESS_TYPES
                       for p in out.values())
            out = {
                pid: p for pid, p in out.items()
                if p['project_access'] in limit
            }
        return out

    def get_subjects(self, project):
        return list_to_dict(
            self('data/projects/%(project)s/subjects' % locals()),
            'id'
        )

    def get_experiments(self, project, subject):
        return list_to_dict(
            # http://www.nitrc.org/ir/data/projects/fcon_1000/subjects/SaintLouis_sub82830/experiments?
            self('data/projects/%(project)s/subjects/%(subject)s/experiments' % locals()),
            'id'
        )

    def get_files(self, project, subject, experiment):
        files = []
        for rec_type in ('scans', 'assessors'):
            url = 'data/projects/%(project)s/subjects/%(subject)s/experiments/%(experiment)s/%(rec_type)s' % \
                      locals()
            recs = self(url)
            files_ = []
            for rec in recs:
                files_.extend(self(url + '/%(id)s/files' % rec, fields_to_check={'title', 'result', 'columns'}))
            for f in files_:
                f['rec_type'] = rec_type
            files.extend(files_)
        return files

    def get_all_files_for_project(self, project, subjects=None, experiments=None):
        for subject in (subjects or self.get_subjects(project)):
            for experiment in (experiments or self.get_experiments(project, subject)):
                for file_ in self.get_files(project, subject, experiment):
                    yield file_