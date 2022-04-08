# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""

"""

from io import StringIO

from datalad.cmd import (
    GitWitlessRunner,
    StdOutErrCapture,
)

from logging import getLogger
lgr = getLogger('datalad.local.gitcredentials')


def _credspec2dict(spec):
    """Parser for git-credential input/output format

    See `man 1 git-credential` (INPUT/OUTPUT FORMAT)

    Parameters
    ----------
    spec : file-like or IO stream

    Returns
    -------
    dict
    """
    attrs = {}
    for line in spec:
        if not line:
            # empty line ends specification
            break
        # protocol violations?
        assert('=' in line)
        assert(line[-1] == '\n')
        k, v = line[:-1].split('=', maxsplit=1)
        # w/o conversion to str this might be a _io.TextWrapper crashing further
        # down the road (for example when passed to re.match):
        attrs[k] = str(v)
    return attrs


class GitCredentialInterface(object):
    """Frontend to `git credential`
    """

    def __init__(self, protocol=None, host=None, path=None, username=None,
                 password=None, url=None, repo=None):
        """
        protocol: str, optional
          The protocol over which the credential will be used (e.g., https).
        host: str, optional
          The remote hostname for a network credential. This includes the port
          number if one was specified (e.g., "example.com:8088").
        path: str, optional
          The path with which the credential will be used. E.g., for accessing
          a remote https repository, this will be the repository’s path on the
          server.
        username: str, optional
          The credential’s username, if we already have one (e.g., from a URL,
          the configuration, the user, or from a previously run helper).
        password: str, optional
          The credential’s password, if we are asking it to be stored.
        url: str, optional
          When this special attribute is read by git credential as 'url', the
          value is parsed as a URL and treated as if its constituent parts were
          read (e.g., url=https://example.com would behave as if
          protocol=https and host=example.com had been provided).
          This can help callers avoid parsing URLs themselves.

          Note that specifying a protocol is mandatory and if the URL doesn’t
          specify a hostname (e.g., "cert:///path/to/file") the credential will
          contain a hostname attribute whose value is an empty string.

          Components which are missing from the URL (e.g., there is no username
          in the example above) will be left unset.
        repo : GitRepo, optional
            Specify to process credentials in the context of a particular
            repository (e.g. to consider a repository-local credential helper
            configuration).
        """
        self._runner = None
        self._repo = repo
        self._credential_props = {}
        for name, var in (('url', url),
                          ('protocol', protocol),
                          ('host', host),
                          ('path', path),
                          ('username', username),
                          ('password', password)):
            if var is None:
                continue
            self._credential_props[name] = var

    def _get_runner(self):
        runner = self._runner or GitWitlessRunner(
            cwd=self._repo.path if self._repo else None)
        self._runner = runner
        return runner

    def _format_props(self):
        props = ''
        for p in self._credential_props:
            val = self._credential_props.get(p)
            if self._credential_props.get(p) is None:
                continue
            props += '{}={}\n'.format(p, val)

        props = props.encode('utf-8')
        if not props:
            props = b'\n'
        return props

    def __getitem__(self, key):
        return self._credential_props.__getitem__(key)

    def __contains__(self, key):
        return self._credential_props.__contains__(key)

    def __repr__(self):
        return repr(self._credential_props)

    def fill(self):
        # TODO we could prevent prompting by setting GIT_ASKPASS=true
        # unclear how to achieve the same on windows
        # would be better to use a special return value for no-prompt
        # with GIT_ASKPASS=true would just be an empty string
        out = self._get_runner().run(
            ['git', 'credential', 'fill'],
            protocol=StdOutErrCapture,
            stdin=self._format_props()
        )
        attrs = _credspec2dict(StringIO(out['stdout']))
        self._credential_props = attrs
        return self

    def approve(self):
        self._get_runner().run(
            ['git', 'credential', 'approve'],
            stdin=self._format_props()
        )

    def reject(self):
        self._get_runner().run(
            ['git', 'credential', 'reject'],
            stdin=self._format_props()
        )


