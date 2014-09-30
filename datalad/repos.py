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

from os.path import join, exists, lexists

from .cmd import Runner, link_file_load
from .files import decompress_file

import logging
lgr = logging.getLogger('datalad.git')

def _esc(filename):
    """Surround filename in "" and escape " in the filename
    """
    filename = filename.replace('"', r'\"').replace('`', r'\`')
    filename = '"%s"' % filename
    return filename

class AnnexRepo(object):
    """Helper to deal with git-annex'ed repositories
    """
    def __init__(self, path, runner=None, description=None):
        """It will initialize the repository if it doesn't exist
        """
        self.path = path
        self.runner = runner or Runner()   # if none provided -- have own

        if not exists(join(path, '.git', 'annex')):
            self.init(description)

    def run(self, cmd, git_cmd="annex"):
        return self.runner.getstatusoutput(
            "cd %s && git %s %s" % (self.path, git_cmd, cmd))

    def write_description(self, description):
        with open(join(self.path, '.git', 'description'), 'w') as f:
            f.write(description + '\n')

    def init(self,  description=""):
        lgr.info("Initializing git annex repository under %s: %s"
                 % (self.path, description))

        status, output = self.runner.getstatusoutput(
            "cd %s && git init && git annex init" % self.path)

        if description:
            lgr.debug("Writing description")
            # dump description
            self.runner.drycall(self.write_description, description)

    def get_indexed_files(self):
        """Helper to spit out a list of indexed files
        """
        gitrepo = git.Repo(self.path)
        index = gitrepo.index
        # if belongs to index
        return [x[0] for x in index.entries.keys()]

    def rm_indexed_file(self, filename):
        """Remove file if it is already under git-annex

        """
        full_filename = join(self.path, filename)
        if not lexists(full_filename):
            return
        # TODO: since in dry_mode things might differ... ?
        # if belongs to index
        if  filename in self.get_indexed_files():
            # and no local changes
            gitrepo = git.Repo(self.path)
            index = gitrepo.index
            if not len(index.diff(None, paths=[filename])):
                lgr.debug("Removing %s without local changes", filename)
                self.runner.drycall(os.unlink, full_filename)
            else:
                lgr.debug("Did not remove %s since there were local changes",
                          filename)

    def add_file(self, annex_filename, href=None, add_mode='auto',
                       annex_opts="", git_add=False):
        """
        If add_mode=='auto' we assume that if file doesn't exist already --
        it should be '--fast' added
        """
        # strip the directory off
        # We delay actual committing to git-annex until later
        annex_opts = annex_opts + ' -c annex.alwayscommit=false'
        full_annex_filename = join(self.path, annex_filename)
        if git_add:
            # TODO: reflect in stats.  Now it would add to _annex_updates
            if not self.runner.dry:
                assert(os.path.exists(full_annex_filename))
            return self.run(_esc(annex_filename), git_cmd="add")

        # The rest for annex logic
        if add_mode == 'auto':
            if exists(full_annex_filename):
                add_mode = "download"
            elif self.runner.dry:
                add_mode = "fast"
                lgr.warning("Cannot deduce auto mode in 'dry' mode. So some actions "
                            "might differ -- assuming 'fast' mode")
            else:
                if href is None:
                    raise ValueError("No file and no href -- can't add to annex")
                add_mode = "fast"

        if href:
            annex_cmd = 'addurl %s --file %s %s %s' \
              % (annex_opts, _esc(annex_filename),
                 {'download': '',
                  'fast': '--fast',
                  'relaxed': '--relaxed'}[add_mode],
                 _esc(href))
        else:
            annex_cmd = 'add %s %s' % (annex_opts, _esc(annex_filename),)

        return self.run(annex_cmd)

def pretreat_archive(filename, archives_re=None):
    """Given a filename deduce either it is an archive and return corresponding "public" filename
    """
    # it might be that we would like to move it
    # or extract it
    # TODO: This might need to be done "on top"
    is_archive = False
    if archives_re:
        res = re.search(archives_re, filename)
        if res:
            is_archive = True
            annex_dir = filename[:res.start()]
            if res.end() < len(res.string):
                annex_dir += filename[res.end:]
            filename = annex_dir   # TODO: "merge" the two
    return is_archive, filename

def annex_file(href,
               incoming_filename, incoming_annex, incoming_updated, is_archive,
               public_filename, public_annex,
               incoming_destiny="auto",
               archives_directories="strip",
               add_mode='auto',
               # TODO!? uncomp_strip_leading_dir=True, #  False; would strip only if 1 directory
               addurl_opts=None,
               runner=None,
               git_add=False,
               ):
    """Annex file, might require download, copying, extraction etc

    Returns
    -------
    Resulting filename under the public_annex
    """
    assert(runner)                        # must be provided
    # convenience shortcuts
    _call = runner.drycall
    fast_mode = add_mode in ['fast', 'relaxed']

    lgr.info("Annexing (mode=%s) %s//%s originating from url=%s present locally under %s//%s"
             % (add_mode, public_annex.path, public_filename,
                href,
                incoming_annex.path, incoming_filename))
    incoming_annex_updated, public_annex_updated = False, False

    full_incoming_filename = join(incoming_annex.path, incoming_filename)
    full_public_filename = join(public_annex.path, public_filename)

    # figure out either in general update is needed
    update_public = incoming_updated or not lexists(full_public_filename)

    # Deal with public part first!
    if update_public:
        ## # TODO: WRONG! we might not have full_incoming_filename == e.g. in fast mode
        ## if not exists(full_incoming_filename) and not runner.dry:
        ##     lgr.error("Cannot update public %s because incoming %s is N/A. Skipping."
        ##               % (public_filename, incoming_filename))
        ##     return False, False         # TODO: or what?

        if is_archive:
            # TODO: what if the directory exist already?  option? yeah --
            # for now we will just REMOVE and recreate with new files
            # otherwise we might like to track in our DB ALL the files
            # extracted from any given archive, so we know which ones to
            # remove selectively
            # TODO#2: what do we do with archives in add_mode==fast?
            #if fast_mode:
            #    raise NotImplementedError("Fast mode for archives is not supported ATM")
            # DONE#2: they should have been downloaded, and check above verifies that
            temp_annex_dir = full_public_filename + ".extract"
            if exists(temp_annex_dir):
                lgr.warn("Found stale temporary directory %s. Removing it first" % temp_annex_dir)
                _call(shutil.rmtree, temp_annex_dir)

            try:
                _call(os.makedirs, temp_annex_dir)
                _call(decompress_file,
                     full_incoming_filename, temp_annex_dir,
                     directories=archives_directories)
            except Exception, e:
                lgr.error("Extraction of %s under %s failed: %s. Skipping."
                          % (full_incoming_filename, temp_annex_dir, e))
                return False, False

            if exists(full_public_filename):
                # TODO: it might be under git/git-annex and require a special treat here?
                lgr.debug("Removing previously present %s" % full_public_filename)
                _call(shutil.rmtree, full_public_filename)

            lgr.debug("Moving %s under %s" % (temp_annex_dir, full_public_filename))
            _call(os.rename, temp_annex_dir, full_public_filename)

            # TODO: some files might need to go to GIT directly, and currently
            #       implemented git_add would not be in effect for content extracted
            #       from archives
            public_annex.add_file(public_filename, add_mode='download', git_add=git_add)
            if not runner.dry:
                public_annex_updated = True

        else:
            # Figure out if anything needs to be done to it
            # TODO: some files might need to go to GIT directly
            # TODO: split "incoming" and "public" handling, so we could
            # perform (redo) 'incoming' -> 'public' actions if necessary, but then also
            # TODO: git annex get (as an option) happen re-publication is needed
            # (e.g. separate out public from incoming)
            ## should come now later with incoming_destiny
            ## incoming_annex.add_file(incoming_filename, href=href, add_mode=add_mode, git_add=git_add)
            # copy via linking (TODO -- option to move, copy?)

            if incoming_annex is not public_annex:
                # MMV in dry mode
                if exists(full_incoming_filename):
                    _call(link_file_load, full_incoming_filename, full_public_filename)
                elif (not fast_mode and lexists(full_incoming_filename)):
                    raise ValueError("Link %s exists but broken -- should have not happened"
                                     % full_incoming_filename)
                else:
                    assert(fast_mode or runner.dry)

            if (incoming_annex is not public_annex) or fast_mode:
                public_annex.rm_indexed_file(public_filename)
                public_annex.add_file(public_filename, href=href, add_mode=add_mode, git_add=git_add)
                if not runner.dry:
                    public_annex_updated = True

    # And after all decide on the incoming destiny
    if incoming_destiny == 'auto':
        incoming_destiny = 'rm' if ((incoming_annex is public_annex) and is_archive) else 'annex'

    if incoming_updated or os.path.lexists(full_incoming_filename):
        # what do we do with the "incoming" archive
        if incoming_destiny == 'rm':
            if is_archive or not fast_mode:
                _call(os.unlink, full_incoming_filename)
            else:
                # Should not be there
                assert(not lexists(full_incoming_filename))
        elif incoming_destiny in ('annex', 'drop'):
            if (incoming_annex is not public_annex) or not fast_mode:
                incoming_annex.rm_indexed_file(incoming_filename)
                if exists(full_incoming_filename) and fast_mode:
                    # git annex would drop the load in --fast mode, so let's not provide 'fast'
                    incoming_annex.add_file(incoming_filename, href=href, git_add=git_add)
                else:
                    # normal
                    incoming_annex.add_file(incoming_filename, href=href, add_mode=add_mode, git_add=git_add)
            if incoming_destiny == 'drop' and exists(full_incoming_filename):
                incoming_annex.run("drop %s" % incoming_filename)
            if not runner.dry:
                incoming_annex_updated = True
        elif incoming_destiny == 'keep':
            pass # do nothing more
        else:
            raise ValueError("Unknown value of incoming_destiny=%r"
                             % incoming_destiny)
    else:
        lgr.debug("Skipping treating incoming %s since either it was not "
                  "updated and/or it doesn't exist" % full_incoming_filename)

    if incoming_annex is public_annex:
        incoming_annex_updated = public_annex_updated = \
            incoming_annex_updated or public_annex_updated

    return incoming_annex_updated, public_annex_updated


def git_commit(path, files=None, msg=""):
    if msg is None:
        msg = 'page2annex: Committing staged changes as of %s' \
               % time.strftime('%Y/%m/%d %H:%M:%S')

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
