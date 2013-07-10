#emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*- 
#ex: set sts=4 ts=4 sw=4 noet:
#------------------------- =+- Python script -+= -------------------------
"""Interfaces to git and git-annex

 COPYRIGHT: Yaroslav Halchenko 2013

 LICENSE: MIT

  Permission is hereby granted, free of charge, to any person obtaining a copy
  of this software and associated documentation files (the "Software"), to deal
  in the Software without restriction, including without limitation the rights
  to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
  copies of the Software, and to permit persons to whom the Software is
  furnished to do so, subject to the following conditions:

  The above copyright notice and this permission notice shall be included in
  all copies or substantial portions of the Software.

  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
  IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
  OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
  THE SOFTWARE.
"""

__author__ = 'Yaroslav Halchenko'
__copyright__ = 'Copyright (c) 2013 Yaroslav Halchenko'
__license__ = 'MIT'

import git
import os
import re
import shutil
import time

from .cmd import getstatusoutput, dry
from .files import decompress_file

import logging
lgr = logging.getLogger('page2annex.git')

class AnnexRepo(object):

    def __init__(self, path, dry_run=False):
        self.path = path
        self.dry_run = dry_run

    def run(self, cmd):
        cmdfull = "cd %s && git annex %s" % (self.path, cmd)
        return getstatusoutput(cmdfull, self.dry_run)

    def dry(self, s):
        return dry(s, self.dry_run)

    def init(self,  description=""):

        lgr.info(self.dry(
            "Initializing git annex repository under %s: %s"
            % (self.path, description)))

        status, output = getstatusoutput(
            "cd %s && git init && git annex init" % self.path, self.dry_run)
        lgr.debug("Successfully initialized")

        if not self.dry_run:
            # dump description
            with open(os.path.join(self.path, '.git', 'description'), 'w') as f:
                f.write(description + '\n')


    def add_file(self, annex_filename, href=None, add_mode='auto',
                       annex_opts=""):
        """
        If add_mode=='auto' we assume that if file doesn't exist already --
        it should be '--fast' added
        """
        #import pydb; pydb.debugger()
        # strip the directory off
        # We delay actual committing to git-annex until later
        annex_opts = annex_opts + ' -c annex.alwayscommit=false'
        if add_mode == 'auto':
            if os.path.exists(annex_filename):
                add_mode = "download"
            else:
                if href is None:
                    raise ValueError("No file and no href -- can't add to annex")
                add_mode = "fast"

        if href:
            annex_cmd = "addurl %s --file %s %s %s" \
              % (annex_opts, annex_filename,
                 {'download': '',
                  'fast': '--fast',
                  'relaxed': '--relaxed'}[add_mode],
                 href)
        else:
            annex_cmd = "add %s %s" % (annex_opts, annex_filename,)

        return self.run(annex_cmd)


def annex_file(href,
               incoming_filename, annex_filename,
               incoming_annex, public_annex,
               archives_destiny=None,
               archives_re=None,
               archives_directories="strip",
               add_mode='auto',
               uncomp_strip_leading_dir=True, #  False; would strip only if 1 directory
               addurl_opts=None,
               dry_run=False
               ):
    """Annex file, might require download, copying, extraction etc

    Returns
    -------
    Resulting filename under the public_annex
    """
    lgr.info("Annexing %s//%s originating from url=%s present locally under %s//%s"
             % (public_annex.path, annex_filename,
                href,
                incoming_annex.path, incoming_filename))

    # it might be that we would like to move it
    # or extract it
    is_archive = False
    if archives_re:
        res = re.search(archives_re, annex_filename)
        if res:
            is_archive = True
            annex_dir = annex_filename[:res.start()]
            if res.end() < len(res.string):
                annex_dir += annex_filename[res.end:]
            full_annex_dir = os.path.join(public_annex.path, annex_dir)
            annex_filename = annex_dir   # TODO: "merge" the two

    full_incoming_filename = os.path.join(incoming_annex.path, incoming_filename)
    full_annex_filename = os.path.join(public_annex.path, annex_filename)

    if is_archive:
        # TODO: what if the directory exist already?  option? yeah --
        # for now we will just REMOVE and recreate with new files
        # otherwise we might like to track in our DB ALL the files
        # extracted from any given archive, so we know which ones to
        # remove selectively 
        temp_annex_dir = full_annex_dir + ".extract"
        os.makedirs(temp_annex_dir)
        decompress_file(full_incoming_filename, temp_annex_dir,
                        directories=archives_directories)
        if os.path.exists(full_annex_dir):
            # TODO: it might be under git/git-annex and require a special treat here
            lgr.debug("Removing previously present %s" % full_annex_dir)
            shutil.rmtree(full_annex_dir)
        os.rename(temp_annex_dir, full_annex_dir)

        # TODO: some files might need to go to GIT directly
        public_annex.add_file(annex_dir)

        # what do we do with the "incoming" archive
        if archives_destiny == 'rm':
            os.unlink(full_incoming_filename)
        elif archives_destiny in ('annex', 'drop'):
            incoming_annex.add_file(incoming_filename, href=href)
            if archives_destiny == 'drop':
                incoming_annex.run("drop %s" % annex_filename)
        elif archives_destiny == 'keep':
            pass # do nothing more
        else:
            raise ValueError("Unknown value of archives_destiny=%r"
                             % archives_destiny)
    else:
        # Figure out if anything needs to be done to it
        # TODO: some files might need to go to GIT directly
        incoming_annex.add_file(incoming_filename, href=href, add_mode=add_mode)
        # copy via linking (TODO -- option to move, copy?)

        if incoming_annex is not public_annex:
            if os.path.exists(full_incoming_filename):
                os.link(full_incoming_filename, full_annex_filename)
            else:
                # assuming --fast mode
                pass
            public_annex.add_file(annex_filename, href=href, add_mode=add_mode)
    return annex_filename


def git_commit(path, files=None, msg=None, dry_run=False):
    if msg is None:
        msg = 'page2annex: Committing staged changes as of %s' \
               % time.strftime('%Y/%m/%d %H:%M:%S')
    if dry_run:
        # Just record this event for logging
        getstatusoutput("GIT COMMIT VIA GIT MODULE PATH=%s FILES=%s"
                        % (path, files), dry_run=dry_run)
        return

    repo = git.Repo(path)

    if files: # smth to add to commit?
        repo.index.add(files)

    # anything staged to be committed
    # it might be invalid at the very beginning ;)
    if not repo.head.is_valid() or len(repo.index.diff(repo.head.commit)):
        #repo.git.commit(m=msg, a=True)
        repo.index.commit(msg)
        repo.index.update()
        assert(not len(repo.index.diff(repo.head.commit)))
        # cmd = "cd %s; git commit -m %r" % (path, msg)
        # status, output = getstatusoutput(cmd, dry_run)
