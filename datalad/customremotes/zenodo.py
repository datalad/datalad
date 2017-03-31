# emacs: -*- mode: python; py-indent-offset: 4; indent-tabs-mode: nil -*-
# vi: set ft=python sts=4 ts=4 sw=4 et:
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Custom remote to upload files directly into zenodo using it as a regular special git-annex remote"""

__docformat__ = 'restructuredtext'

import json
import logging
import os
import requests

lgr = logging.getLogger('datalad.customremotes.zenodo')

from ..utils import swallow_logs
from .base import AnnexCustomRemote
from ..dochelpers import exc_str

from ..downloaders.providers import Providers
from .main import main as super_main
from ..utils import md5sum
from ..downloaders.http import HTTPDownloader
from ..ui import ui
from ..ui.progressbars import FileReadProgressbar

API_URLs = {
    'sandbox': "https://sandbox.zenodo.org/api/",
    'default': "https://zenodo.org/api/"
}


class ZenodoAnnexCustomRemote(AnnexCustomRemote):
    """TODO
    """

    AVAILABILITY = "global"
    SUPPORTED_SCHEMES = ()
    SUPPORTED_TRANSFERS = ("RETRIEVE", "STORE")

    def __init__(self, **kwargs):
        super(ZenodoAnnexCustomRemote, self).__init__(**kwargs)

        self._api_url = None
        self._token = None
        self._deposition_id = None

    #
    # Helper methods

    @property
    def token(self):
        if self._token is None:
            providers = Providers.from_config_files()
            provider = providers.get_provider(self.api_url)
            credential = provider.credential
            self._token = credential().get('token')
        return self._token

    @property
    def api_url(self):
        if self._api_url is None:
            api_url = self.req_GETCONFIG('api_url')
            if api_url in API_URLs:
                api_url = API_URLs[api_url]
            if not api_url:
                API_URL = API_URLs['default']
                self.debug(
                    "api_url was not set for the special remote -- "
                    "assuming %s" % API_URL)
                api_url = API_URL
            self._api_url = api_url
        return self._api_url

    @property
    def deposition_id(self):
        if self._deposition_id is None:
            self._deposition_id = self.req_GETCONFIG('deposition_id')
        return self._deposition_id

    def _requests_call(self, m, url, success=None, **kwargs):
        """A wrapper around requests calls
        
        to interpolate deposition_id, do basic checks and conversion
        """
        url_ = self.api_url + url
        if '%s' in url:
            url_ = url_ % self.deposition_id

        if m not in (requests.get,) and 'headers' not in kwargs:
            kwargs['headers'] = {"Content-Type": "application/json"}

        r = m(
            url_,
            params={'access_token': self.token},
            **kwargs
        )
        status_code = r.status_code
        j = r.json() if r.content else {}
        if (success is not "donotcheck") and \
            ((success and status_code not in success)
              or (not success and status_code >= 400)):
            message = j.get('message', '') if isinstance(j, dict) else ''
            msg = "Got return code %(status_code)s for %(m)s(%(url_)s, " \
                  "%(kwargs)s). %(message)s" % locals()
            raise RuntimeError("Error status from zenodo: %s" % msg)
        return j, status_code

    def _put(self, *args, **kwargs):
        return self._requests_call(requests.put, *args, **kwargs)

    def _post(self, *args, **kwargs):
        return self._requests_call(requests.post, *args, **kwargs)

    def _get(self, *args, **kwargs):
        return self._requests_call(requests.get, *args, **kwargs)

    def _delete(self, *args, **kwargs):
        return self._requests_call(requests.delete, *args, **kwargs)

    def _init_zenodo_metadata(self):
        rec = {
            'uuid': self.repo.uuid,
        }
        config = self.repo.config
        creator = {
            k: config.get("user.%s" % k)
            for k in ('name', 'orcid', 'affiliation')
            if config.get("user.%s" % k)
        }
        data = {
            'metadata': {
                'title': 'DataLad dataset UUID %(uuid)s (data)' % rec,
                'upload_type': 'dataset',
                'description': """\
This is a git annex special remote providing data files for the DataLad 
dataset 
UUID %(uuid)s. Git-annex repository to provide access to this collection of 
files can be cloned from TODO""" % rec,
                'creators': [creator],
            }
        }

        # additionally if user provided/stored configuration
        for k in 'access_right', 'license', 'embargo_date', \
                 'access_conditions':
            v = self.req_GETCONFIG(k)
            if v:
                data['metadata'][k] = v
        # there is more cool fields but they could just enter them on zenodo

        r, _ = self._put('deposit/depositions/%s', data=json.dumps(data))

    #
    # Protocol implementation
    #

    def _initremote(self, *args):
        """Custom initialization of the special custom remote."""

        deposition_id = self.deposition_id
        if deposition_id is not None:
            # it was already setup - nothing for us to do again
            return

        self.req_SETCONFIG('api_url', self.api_url)

        r, _ = self._post('deposit/depositions', json={})
        if 'id' not in r:
            raise ValueError("Should have obtained an id for the new deposition")
        self._deposition_id = r['id']
        self.req_SETCONFIG('deposition_id', self._deposition_id)

        self._init_zenodo_metadata()

    def _prepare(self, *args):
        """Prepare special custom remote."""
        # # Check the deposition to see if we could still submit anything there
        # # but actually we probably shouldn't do it here!
        # r, _ = self._get("deposit/depositions/%s")
        # if r['submitted']:
        #     self.error("Deposition was already submitted -- we will not be able to modify it.")

        # make sure that we have all needed information which could also be queried
        # from git-annex
        assert self.token
        assert self.deposition_id
        assert self.api_url

    def _transfer(self, cmd, key, path):

        # TODO: We might want that one to be a generator so we do not bother requesting
        # all possible urls at once from annex.
        urls = self.get_URLS(key)

        if self._last_url in urls:
            # place it first among candidates... some kind of a heuristic
            urls.pop(self._last_url)
            urls = [self._last_url] + urls

        # TODO: priorities etc depending on previous experience or settings

        for url in urls:
            try:
                downloaded_path = self._providers.download(
                    url, path=path, overwrite=True
                )
                lgr.info("Successfully downloaded %s into %s" % (url, downloaded_path))
                self.send('TRANSFER-SUCCESS', cmd, key)
                return
            except Exception as exc:
                self.debug("Failed to download url %s for key %s: %s" % (url, key, exc_str(exc)))

        self.send('TRANSFER-FAILURE', cmd, key,
                  "Failed to download from any of %d locations" % len(urls))

    def _handle_file_without_id(self, key, fpath=None):
        # Let's download full list of files
        lgr.debug(
            "Need to figure out file_id for key %s, downloading list of all files",
            key
        )
        file_recs, _ = self._get('deposit/depositions/%s/files')
        # find one -- should be only one
        file_recs_matched = list(filter(lambda r: r['filename'] == key, file_recs))
        if len(file_recs_matched) > 2:
            raise RuntimeError(
                "There should no two files with the same name. Got: %s"
                % str(file_recs_matched)
            )
        elif len(file_recs_matched):
            file_rec = file_recs_matched[0]
        else:
            return None

        checksum = None
        # we could verify checksum directly if key is MD5
        if key.startswith('MD5'):
            checksum = key.rsplit('--', 1)[1].split('.', 1)[0]
        elif fpath and os.path.exists(fpath):
            checksum = md5sum(fpath)
        if checksum and file_rec['checksum'] != checksum:
            raise RuntimeError(
                "Key %(filename)s seems to have different checksum on zenodo: %(checksum)s"
                % file_rec
            )
        return file_rec.get('id', None)

    def _get_file_id(self, key, fixup=False):
        """Files on zenodo have their own ids.  
        
        This one gets it from what we stored in git-annex and if not found, and 
        fixup then tries to get it from zenodo, and raises exception if fails
        """
        file_id = self.req_GETSTATE(key)
        if not file_id and fixup:
            file_id = self._handle_file_without_id(key)
            if not file_id:
                raise RuntimeError(
                    "Cannot figure out file id for key %s" % key)
        return file_id

    def _transfer(self, cmd, key, fpath):
        if cmd == 'STORE':
            # upload
            data = {'filename': key}
            open_file = open(fpath, 'rb')
            pbar = ui.get_progressbar(label=key, fill_text=fpath,
                                      total=os.stat(fpath).st_size)
            # to be able to report progress we would like to decorate
            # open_file so we could update pbar
            # TODO: this one is not effective really but also
            #       causes filename on remote end to be just 'file'
            #       so it seems that the filename provided in data
            #       gets simply ignored

            #open_file = FileReadProgressbar(open_file, pbar)
            files = {'file': open_file}
            # we might have that file uploaded but did not record/know
            # the id
            r, _ = self._post('deposit/depositions/%s/files',
                              headers=None,
                              success='donotcheck',
                              data=data, files=files)
            # TODO: if key is MD5 we could compare to r['checksum']
            # store key as the 'state'
            if not isinstance(r, dict):
                assert len(r) == 1  # just a single item uploaded
                r = r[0]
            if r.get('status', 0) == 403:
                self.send('TRANSFER-FAILURE', cmd, key, \
                          "Permission denied -- TODO: check if already published")
            assert r['filename'] == key
            message = r.get('message')
            if message and 'Filename already exists' in message:
                file_id = self._handle_file_without_id(key, fpath)
            else:
                file_id = r['id']
            assert file_id
            self.req_SETSTATE(key, file_id)
        elif cmd == 'RETRIEVE':
            file_id = self._get_file_id(key, fixup=True)
            # retrieve its record and download from the url provided
            file_rec, _ = self._get('deposit/depositions/%s/files/' + file_id)
            download_url = file_rec.get('links', {}).get('download', None)
            if not download_url:
                raise RuntimeError("Was not provided download url in %s" % str(file_rec))
            file_size = file_rec.get('size', None)

            # TODO: create a proper "authenticator" for zenodo style authentication
            # and use it throughout instead of ad-hoc access_token here.
            # - also we might finally want to marry our authenticators with
            #   native requests approach: http://docs.python-requests.org/en/v0.11.1/user/advanced/#custom-authentication
            downloader = HTTPDownloader()
            with swallow_logs(new_level=logging.WARN):
                if not downloader.download(
                    download_url + "?access_token=%s" % self.token,
                    fpath, size=file_size
                ):
                    raise IOError("Failed to download %s" % download_url)
        self.send('TRANSFER-SUCCESS', cmd, key)

    def req_REMOVE(self, key):
        """
        REMOVE-SUCCESS Key
            Indicates the key has been removed from the remote. May be returned if the remote didn't have the key at the point removal was requested.
        REMOVE-FAILURE Key ErrorMsg
            Indicates that the key was unable to be removed from the remote.
        """
        lgr.debug("VERIFYING key %s" % key)
        # get file id which we should have recorded into the state
        try:
            file_id = self._get_file_id(key, fixup=True)
        except RuntimeError:
            # if we tried to fix up but failed, most likely it is just not there
            self.send("REMOVE-SUCCESS", key)
            return
        if file_id:
            try:
                r, _ = self._delete('deposit/depositions/%s/files/' + file_id)
                resp = 'SUCCESS'
            except Exception as exc:
                if 'The specified object does not exist ' in str(exc):
                    # was removed already -- we are good
                    resp = 'SUCCESS'
                else:
                    raise
            if resp == 'SUCCESS' and file_id:
                self.req_SETSTATE(key, '')
            self.send("REMOVE-" + resp, key)
        else:
            self.send("REMOVE-FAILURE", key, "Could not determine the key")

    def req_CHECKPRESENT(self, key):
        """Check if copy is available

        Replies

        CHECKPRESENT-SUCCESS Key
            Indicates that a key has been positively verified to be present in
            the remote.
        CHECKPRESENT-FAILURE Key
            Indicates that a key has been positively verified to not be present
            in the remote.
        CHECKPRESENT-UNKNOWN Key ErrorMsg
            Indicates that it is not currently possible to verify if the key is
            present in the remote. (Perhaps the remote cannot be contacted.)
        """
        lgr.debug("VERIFYING key %s" % key)
        # get file id which we should have recorded into the state
        key_id = self._get_file_id(key)
        if key_id:
            # we could check that fella by its id url
            # TODO: we could use our http provider probably and its get_status
            #from datalad.downloaders.http import HTTPDownloader
            #downloader = HTTPDownloader()
            #downloader.get_downloader_session(headers={})
            try:
                r, _ = self._get('deposit/depositions/%s/files/' + key_id)
            except Exception as exc:
                if 'The requested URL was not found on the server' in str(exc):
                    r = {}
                else:
                    raise
            resp = 'SUCCESS' if r.get('filename', '') == key else 'FAILURE'
            self.send("CHECKPRESENT-" + resp, key)
        else:
            #self.send("CHECKPRESENT-UNKNOWN", key, "No key associated yet, so most likely not there")
            self.send("CHECKPRESENT-FAILURE", key)

    def cmd_publish(self, args):
        assert not args, "not expecting any args for publish. Got %s" % str(args)
        # since we need to communicate to annex
        self._prepare()
        if not ui.yesno(
            """\
Published on Zenodo datasets acquire publicly visible URL, doi, etc. Also, 
depending on the access_type, files could be fetched from regular URLs which 
we will assign to every file.  But you will not be able to introduce any further
changes to the uploaded files""",
            title='Are you sure you want to finalize/publish your Zenodo dataset?'
        ):
            return
        import pdb; pdb.set_trace()
        # and now we can officially publish!
        r = self._post('deposit/depositions/%s/actions/publish')
        # assign URLs for all files so people could download directly from the web
        # report back URL
        pass

def main():
    """cmdline entry point"""
    super_main(backend="zenodo")
