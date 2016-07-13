# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Interface for a generic template in which arguments are specified by the user"""

__docformat__ = 'restructuredtext'



from os import makedirs
from .base import Interface
from os.path import exists, curdir, join as opj
from collections import OrderedDict

from ..support.gitrepo import GitRepo
from ..support.param import Parameter
from ..support.constraints import EnsureStr, EnsureNone
from ..consts import CRAWLER_META_DIR, CRAWLER_META_CONFIG_FILENAME
from ..support.configparserinc import SafeConfigParserWithIncludes
from ..crawler.pipeline import load_pipeline_from_template

from logging import getLogger
lgr = getLogger('datalad.api.crawl_init')
CRAWLER_PIPELINE_SECTION = 'crawl:pipeline'

class CrawlInit(Interface):
    """
    Allows user to specify template and function to generate a pipeline

    Examples:

    $ datalad crawl-init \
        --template openfmri \
        --func superdataset_pipeline

    $ datalad crawl-init \
        --template fcptable \
        dataset=Baltimore tarballs=True
    """
    _params_ = dict(
        template=Parameter(
            args=("-t", "--template"),
            action="store",
            constraints=EnsureStr() | EnsureNone(),
            doc="""flag if template is specified by user"""),
        template_func=Parameter(
            args=("-f", "--func"),
            action="store",
            doc="""flag if function is specified by user"""),
        template_kwargs=Parameter(
            args=("args",),
            nargs="*",
            type=OrderedDict or list,
            doc="""keyword arguments to pass into the template function generating actual pipeline,
            organized in an ordered dict"""),
        path=Parameter(
            args=("path",),
            action="store",
            doc="""specify directory in which to save file, default is curdir"""),
        commit=Parameter(
            args=("-c", "--commit"),
            action="store_true",
            doc="""flag is user wants to commit file into git repo""")
    )

    @staticmethod
    def __call__(template=None, template_func=None, template_kwargs=None, path=curdir, commit=False):

        lgr.debug("Creating crawler configuration for template %s under %s",
                  template, path)

        crawl_config_dir = opj(path, CRAWLER_META_DIR)
        if not exists(crawl_config_dir):
            lgr.log(2, "Creating %s", crawl_config_dir)
            makedirs(crawl_config_dir)

        crawl_config = opj(crawl_config_dir, CRAWLER_META_CONFIG_FILENAME)
        crawl_config_repo_path = opj(CRAWLER_META_DIR, CRAWLER_META_CONFIG_FILENAME)
        cfg_ = SafeConfigParserWithIncludes()
        cfg_.add_section(CRAWLER_PIPELINE_SECTION)

        if template:
            cfg_.set(CRAWLER_PIPELINE_SECTION, 'template', template)

        if template_func:
            cfg_.set(CRAWLER_PIPELINE_SECTION, 'func', template_func)

        if template_kwargs:
            if type(template_kwargs) == dict:
                template_kwargs = OrderedDict(sorted(template_kwargs.items()))
                for k, v in template_kwargs.items():
                    cfg_.set(CRAWLER_PIPELINE_SECTION, "_" + k, str(v))
            if type(template_kwargs) == list:
                for item in template_kwargs:
                    variable, name = item.split('=', 1)
                    cfg_.set(CRAWLER_PIPELINE_SECTION, "_"+variable, name)

        with open(crawl_config, 'w') as f:
            cfg_.write(f)

        if commit:
            repo = GitRepo(path)
            repo.add(crawl_config_repo_path)
            if repo.dirty:
                repo.commit("Initialized crawling configuration to use template %s" % template)
            else:
                lgr.debug("Repository is not dirty -- not committing")



