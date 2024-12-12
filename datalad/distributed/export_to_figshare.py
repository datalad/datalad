# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""export a dataset as a TAR/ZIP archive to figshare"""

__docformat__ = 'restructuredtext'

import logging

from datalad.interface.base import (
    Interface,
    build_doc,
)
from datalad.interface.results import get_status_dict
from datalad.utils import unlink

lgr = logging.getLogger('datalad.distributed.export_to_figshare')


class FigshareRESTLaison(object):
    """A little helper to provide minimal interface to interact with Figshare
    """
    API_URL = 'https://api.figshare.com/v2'

    def __init__(self):
        self._token = None
        from datalad.ui import ui
        self.ui = ui  # we will be chatty here

    @property
    def token(self):
        if self._token is None:
            from datalad.downloaders.providers import Providers
            providers = Providers.from_config_files()
            provider = providers.get_provider(self.API_URL)
            credential = provider.credential
            self._token = credential().get('token')
        return self._token

    def __call__(self, m, url, data=None, success=None, binary=False,
                 headers=None, return_json=True):
        """A wrapper around requests calls

        to interpolate deposition_id, do basic checks and conversion
        """
        import json
        if '://' not in url:
            url_ = self.API_URL + '/' + url
        else:
            url_ = url

        headers = headers or {}
        if data is not None and not binary:
            data = json.dumps(data)
            headers["Content-Type"] = "application/json"
        headers['Authorization'] = "token %s" % self.token

        lgr.debug(
            "Submitting %s request to %s with data %s (headers: %s)",
            m.__name__, url_, data, 'sanitized'  # headers
        )
        r = m(url_, data=data, headers=headers)
        status_code = r.status_code
        if (success != "donotcheck") and \
                ((success and status_code not in success)
                 or (not success and status_code >= 400)):
            msg = "Got return code %(status_code)s for %(m)s(%(url_)s." \
                  % locals()
            raise RuntimeError("Error status %s" % msg)

        if return_json:
            return r.json() if r.content else {}
        else:
            return r.content

    def put(self, *args, **kwargs):
        import requests
        return self(requests.put, *args, **kwargs)

    def post(self, *args, **kwargs):
        import requests
        return self(requests.post, *args, **kwargs)

    def get(self, *args, **kwargs):
        import requests
        return self(requests.get, *args, **kwargs)

    def upload_file(self, fname, files_url):
        # In v2 API seems no easy way to "just upload".  Need to initiate,
        # do uploads
        # and finalize
        # TODO: check if the file with the same name already available, and offer
        # to remove/prune it
        import os

        from datalad.ui import ui
        from datalad.utils import md5sum
        file_rec = {'md5': md5sum(fname),
                    'name': os.path.basename(fname),
                    'size': os.stat(fname).st_size
                    }
        # Initiate upload
        j = self.post(files_url, file_rec)
        file_endpoint = j['location']
        file_info = self.get(file_endpoint)
        file_upload_info = self.get(file_info['upload_url'])

        pbar = ui.get_progressbar(label=fname,  # fill_text=f.name,
                                  total=file_rec['size'])
        with open(fname, 'rb') as f:
            for part in file_upload_info['parts']:
                udata = dict(file_info, **part)
                if part['status'] == 'PENDING':
                    f.seek(part['startOffset'])
                    data = f.read(part['endOffset'] - part['startOffset'] + 1)
                    url = '{upload_url}/{partNo}'.format(**udata)
                    ok = self.put(url, data=data, binary=True, return_json=False)
                    assert ok == b'OK'
                pbar.update(part['endOffset'], increment=False)
            pbar.finish()

        # complete upload
        jcomplete = self.post(file_endpoint, return_json=False)
        return file_info

    def get_article_ids(self):
        articles = self.get('account/articles')
        ids = []
        for item in articles or []:
            self.ui.message(' {id} {url} - {title}'.format(**item))
            ids.append(item['id'])
        return ids

    def create_article(self, title):
        data = {
            'title': title
        }
        # we could prefill more fields interactively if desired
        result = self.post('account/articles', data=data)
        result = self.get(result['location'])
        return result


def _get_default_title(dataset):
    """Create default title as dataset directory[#UUID][@version]
    with any of [] missing if not defined
    """
    from ..support.path import basename
    title = basename(dataset.path)
    if dataset.id:
        title += "#{dataset.id}".format(**locals())
    version = dataset.repo.describe()
    if version:
        title += "@{version}".format(**locals())
    # 3 is minimal length. Just in case there is no UUID or version and dir
    # is short
    if len(title) < 3:
        title += "0"*(3 - len(title))
    return title


def _enter_title(ui, dataset):
    default = _get_default_title(dataset)
    while True:
        title = ui.question(
            "Please enter the title (must be at least 3 characters long).",
            title="New article",
            default=default
        )
        if len(title) < 3:
            ui.error("Title must be at least 3 characters long.")
        else:
            return title


@build_doc
class ExportToFigshare(Interface):
    """Export the content of a dataset as a ZIP archive to figshare

    Very quick and dirty approach.  Ideally figshare should be supported as
    a proper git annex special remote.  Unfortunately, figshare does not support
    having directories, and can store only a flat list of files.  That makes
    it impossible for any sensible publishing of complete datasets.

    The only workaround is to publish dataset as a zip-ball, where the entire
    content is wrapped into a .zip archive for which figshare would provide a
    navigator.
    """

    from datalad.distribution.dataset import (
        EnsureDataset,
        datasetmethod,
    )
    from datalad.interface.base import eval_results
    from datalad.support.constraints import (
        EnsureChoice,
        EnsureInt,
        EnsureNone,
        EnsureStr,
    )
    from datalad.support.param import Parameter

    _params_ = dict(
        dataset=Parameter(
            args=("-d", "--dataset"),
            doc=""""specify the dataset to export. If no dataset is given, an
            attempt is made to identify the dataset based on the current
            working directory.""",
            constraints=EnsureDataset() | EnsureNone()),
        filename=Parameter(
            args=("filename",),
            metavar="PATH",
            nargs='?',
            doc="""File name of the generated ZIP archive. If no file name is
            given the archive will be generated in the top directory
            of the dataset and will be named: datalad_<dataset_uuid>.zip.""",
            constraints=EnsureStr() | EnsureNone()),
        no_annex=Parameter(
            args=("--no-annex",),
            action="store_true",
            doc="""By default the generated .zip file would be added to annex,
            and all files would get registered in git-annex to be available
            from such a tarball. Also upon upload we will register for that
            archive to be a possible source for it in annex. Setting this flag
            disables this behavior."""),
        missing_content=Parameter(
            args=("--missing-content",),
            doc="""By default, any discovered file with missing content will
            result in an error and the plugin is aborted. Setting this to
            'continue' will issue warnings instead of failing on error. The
            value 'ignore' will only inform about problem at the 'debug' log
            level. The latter two can be helpful when generating a TAR archive
            from a dataset where some file content is not available
            locally.""",
            constraints=EnsureChoice("error", "continue", "ignore")),
        # article_id=Parameter(
        #     args=("--project-id",),
        #     metavar="ID",
        #     doc="""If given, article (if article_id is not provided) will be
        #     created in that project.""",
        #     constraints=EnsureInt() | EnsureNone()),
        article_id=Parameter(
            args=("--article-id",),
            metavar="ID",
            doc="""Which article to publish to.""",
            constraints=EnsureInt() | EnsureNone()),
    )

    @staticmethod
    @datasetmethod(name='export_to_figshare')
    @eval_results
    # TODO*: yet another former plugin with dataset first -- do we need that???
    def __call__(filename=None,
                 *,
                 dataset=None,
                 missing_content='error', no_annex=False,
                 # TODO: support working with projects and articles within them
                 # project_id=None,
                 article_id=None):
        import logging
        lgr = logging.getLogger('datalad.plugin.export_to_figshare')

        from datalad.api import (
            add_archive_content,
            export_archive,
        )
        from datalad.distribution.dataset import require_dataset
        from datalad.support.annexrepo import AnnexRepo
        from datalad.ui import ui

        dataset = require_dataset(dataset, check_installed=True,
                                  purpose='export to figshare')

        if not isinstance(dataset.repo, AnnexRepo):
            raise ValueError(
                "%s is not an annex repo, so annexification could be done"
                % dataset
            )

        if dataset.repo.dirty:
            yield get_status_dict(
                'export_to_figshare',
                ds=dataset,
                status='impossible',
                message=(
                    'clean dataset required to export; '
                    'use `datalad status` to inspect unsaved changes'))
            return
        if filename is None:
            filename = dataset.path
        lgr.info(
            "Exporting current tree as an archive under %s since figshare "
            "does not support directories",
            filename
        )
        archive_out = next(
            export_archive(
                dataset=dataset,
                filename=filename,
                archivetype='zip',
                missing_content=missing_content,
                return_type="generator"
            )
        )
        assert archive_out['status'] == 'ok'
        fname = str(archive_out['path'])

        lgr.info("Uploading %s to figshare", fname)
        figshare = FigshareRESTLaison()

        if not article_id:
            # TODO: ask if it should be an article within a project
            if ui.is_interactive:
                # or should we just upload to a new article?
                if ui.yesno(
                    "Would you like to create a new article to upload to?  "
                    "If not - we will list existing articles",
                    title="Article"
                ):
                    article = figshare.create_article(
                        title=_enter_title(ui, dataset)
                    )
                    lgr.info(
                        "Created a new (private) article %(id)s at %(url_private_html)s. "
                        "Please visit it, enter additional meta-data and make public",
                        article
                    )
                    article_id = article['id']
                else:
                    article_id = int(ui.question(
                        "Which of the articles should we upload to.",
                        choices=list(map(str, figshare.get_article_ids()))
                    ))
            if not article_id:
                raise ValueError("We need an article to upload to.")

        file_info = figshare.upload_file(
            fname,
            files_url='account/articles/%s/files' % article_id
        )

        if no_annex:
            lgr.info("Removing generated tarball")
            unlink(fname)
        else:
            # I will leave all the complaining etc to the dataset add if path
            # is outside etc
            lgr.info("'Registering' %s within annex", fname)
            repo = dataset.repo
            repo.add(fname, git=False)
            key = repo.get_file_annexinfo(fname)['key']
            lgr.info("Adding URL %(download_url)s for it", file_info)
            repo.call_annex([
                "registerurl", '-c', 'annex.alwayscommit=false',
                key, file_info['download_url']])

            lgr.info("Registering links back for the content of the archive")
            add_archive_content(
                fname,
                dataset=dataset,
                delete_after=True,  # just remove extracted into a temp dir
                allow_dirty=True,  # since we have a tarball
                commit=False  # we do not want to commit anything we have done here
            )

            lgr.info("Removing generated and now registered in annex archive")
            repo.drop(key, key=True, options=['--force'])
            repo.remove(fname, force=True)  # remove the tarball

            # if annex in {'delete'}:
            #     dataset.repo.remove(fname)
            # else:
            #     # kinda makes little sense I guess.
            #     # Made more sense if export_archive could export an arbitrary treeish
            #     # so we could create a branch where to dump and export to figshare
            #     # (kinda closer to my idea)
            #     dataset.save(fname, message="Added the entire dataset into a zip file")

        # TODO: add to downloader knowledge about figshare token so it could download-url
        # those zipballs before they go public
        yield dict(
            status='ok',
            # TODO: add article url (which needs to be queried if only ID is known
            message="Published archive {}".format(
                file_info['download_url']),
            file_info=file_info,
            path=dataset,
            action='export_to_figshare',
            logger=lgr
        )
