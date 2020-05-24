#!/usr/bin/env python

import os
import hashlib
import subprocess
from pathlib import Path

# for debugging: (consider enable(display=0, logdir=/log/path/)  later on)
# import cgi
#import cgitb
#cgitb.enable()  # note: logdir="/tmp/logs" didn't work locally (why?)
# cgi.test()


# Requested URI is supposed to point to an annex key (dirhashmixed),
# i.e. something like
# /store/814/cb17e-95b2-11ea-8bc2-d14d8c08eceb/annex/objects/km/xp/MD5E-s5--a2e5e988620bbe17ef14dfd37e4d86ca/MD5E-s5--a2e5e988620bbe17ef14dfd37e4d86ca

# In simplest case this is exactly what we need to look at

class KeyNotFoundError(Exception):
    pass


class AnnexObject(object):
    """

    """

    def __init__(self, request_path, path_prefix):
        """

        :param request_path:
        :param path_prefix:
        """
        path_prefix = Path(path_prefix)

        uri_parts = request_path.split('/')
        self.key = uri_parts[-1]
        # Note, that uri_parts[1:-6] derives from:
        # - URI has to start with '/', therefore split() results starts with
        #   empty string
        # - 6 substracted levels: annex/objects/tree_1/tree_2/key_dir/key_file
        ds_dir = path_prefix.joinpath(*uri_parts[1:-6])

        self.archive_path = ds_dir / 'archives' / 'archive.7z'

        # We need to figure where to actually look for a key file. Currently a
        # dataset may use dirhashlower or dirhashmixed to build its
        # annex/objects tree.
        # See https://git-annex.branchable.com/internals/hashing/
        ds_layout_version = \
            (ds_dir / 'ria-layout-version').read_text().strip().split('|')[0]
        if ds_layout_version == '1':
            # dataset representation uses dirhashlower
            md5 = hashlib.md5(self.key.encode()).hexdigest()
            self.object_path = Path(md5[:3]) / md5[3:] / self.key / self.key
            self.file_path = ds_dir / 'annex' / 'objects' / self.object_path

        elif ds_layout_version == '2':
            # dataset representation uses dirhashmixed; this is what we expect
            # the original URI to be already. Note, that URI is absolute while
            # we need to look at it as a relative path.
            self.file_path = path_prefix.joinpath(*uri_parts[1:])
            self.object_path = Path(uri_parts[-4]).joinpath(*uri_parts[-3:])
        else:
            # TODO: Proper status
            raise ValueError("layout: %s" % ds_layout_version)

        self._exists = None
        self._in_archive = None

    def in_archive(self):

        def check_archive():
            if not self.archive_path.exists():
                # no archive, no file
                return False
            # TODO: ultimately those paths come from user input (the request).
            #       What exactly do we need to make sure at this point wrt
            #       security?
            loc = str(self.object_path)
            arc = str(self.archive_path)

            try:
                res = subprocess.run(['7z', 'l', arc, loc],
                                     stdout=subprocess.PIPE,
                                     check=True)
            except subprocess.CalledProcessError:
                # - if we can't run that, we don't have access
                # - includes missing 7z executable
                return False

            return loc in res.stdout.decode()

        # store result; note that within this script we respond to a single
        # request
        if self._in_archive is None:
            self._in_archive = check_archive()
        return self._in_archive

    def in_object_tree(self):

        # store result; note that within this script we respond to a single
        # request
        if self._exists is None:
            self._exists = self.file_path.exists()
        return self._exists

    def is_present(self):

        # TODO: What do missing read permissions lead to with those checks?
        #       => we may not want to reveal whether a key is here if requesting
        #       user has no permission to read that key and/or dataset.

        return self.in_object_tree() or self.in_archive()

    def get(self):

        if self.in_object_tree():
            return self.file_path.read_bytes()
        elif self.in_archive():
            res = subprocess.run(['7z', 'x', '-so',
                                  str(self.archive_path),
                                  str(self.object_path)],
                                 stdout=subprocess.PIPE)
            return res.stdout
        else:
            raise KeyNotFoundError

    def size(self):

        # see: https://git-annex.branchable.com/internals/key_format/
        key_parts = self.key.split('--')
        key_fields = key_parts[0].split('-')
        parsed = {field[0]: int(field[1:]) if field[1:].isdigit() else None
                  for field in key_fields[1:]
                  if field[0] in "sSC"}

        # don't lookup the dict for the same things several times;
        # Is there a faster (and more compact) way of doing this? Note, that
        # locals() can't be updated.
        s = parsed.get('s')
        S = parsed.get('S')
        C = parsed.get('C')

        if S is None and C is None:
            return s  # also okay if s is None as well -> no size to report
        elif s is None:
            # s is None, while S and/or C are not.
            raise ValueError("invalid key: {}".format(self.key))
        elif S and C:
            if C <= int(s / S):
                return S
            else:
                return s % S
        else:
            # S or C are given with the respective other one missing
            raise ValueError("invalid key: {}".format(self.key))


# TODO: better SCRIPT_NAME and check REQUEST has no parameters?
# TODO: What's CONTEXT_DOCUMENT_ROOT vs  DOCUMENT_ROOT ?
key_object = AnnexObject(os.environ.get("REQUEST_URI"),
                         os.environ.get("CONTEXT_DOCUMENT_ROOT"))

method = os.environ.get("REQUEST_METHOD")

header_fields = dict()
content = None

if method == "GET":
    try:
        content = key_object.get()
        header_fields["Content-Type"] = "application/octet-stream"
        header_fields["Content-Disposition"] = "attachment; filename=\"{}\"" \
                                               "".format(key_object.key)
        length = None
        try:
            length = key_object.size()
            header_fields["Content-Length"] = str(length)
        except ValueError:
            # invalid key
            # TODO: for now just no size info
            #       but:
            #       we might want to consider checking this before hand and
            #       reject to serve sth that is based on an invalid key
            pass

        # TODO: ETag header field using the key itself?

    except KeyNotFoundError:
        header_fields["Status"] = "404 Not Found"
        header_fields["Content-Type"] = "text/html"
        content = "<h1>{}</h1>".format(header_fields["Status"])

elif method == "HEAD":
    # Check key availability and respond accordingly
    # TODO: - No read permission -> Status?
    #       - "200 OK" or "302 Found"?

    if key_object.is_present():
        header_fields["Status"] = "200 OK"
        header_fields["Content-Type"] = "application/octet-stream"
        length = None
        try:
            length = key_object.size()
            header_fields["Content-Length"] = str(length)
        except ValueError:
            # invalid key
            # TODO: for now just no size info
            #       but:
            #       we might want to consider checking this before hand and
            #       reject to serve sth that is based on an invalid key
            pass

    else:
        header_fields["Status"] = "404 Not Found"
        header_fields["Content-Type"] = "text/html"
        content = "<h1>{}</h1>".format(header_fields["Status"])

else:
    # TODO: Proper status
    raise ValueError

for field, value in header_fields.items():
    print("{}: {}".format(field, value))
print("")  # end header
if content:
    if isinstance(content, bytes):
        import sys
        sys.stdout.flush()
        sys.stdout.buffer.write(content)
        sys.stdout.flush()
    else:
        print(content)
