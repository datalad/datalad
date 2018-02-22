# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
""""""

__docformat__ = 'restructuredtext'


import logging

from os.path import dirname
from os.path import basename
from os.path import isdir
from os.path import join as opj

from glob import glob

from datalad import cfg
from datalad.interface.base import Interface
from datalad.interface.utils import eval_results
from datalad.interface.base import build_doc

from datalad.dochelpers import exc_str
from datalad.utils import assure_list

from datalad.support.param import Parameter
from datalad.support.constraints import EnsureNone

from datalad.distribution.dataset import EnsureDataset
from datalad.distribution.dataset import datasetmethod


lgr = logging.getLogger('datalad.interface.serve')


def _get_webapps():
    locations = (
        dirname(__file__),
        cfg.obtain('datalad.locations.system-webapps'),
        cfg.obtain('datalad.locations.user-webapps'))
    return {basename(e): {'directory': e}
            for webappdir in locations
            for e in glob(opj(webappdir, '[!_]*'))
            if isdir(e)}


def _import_webapp(filepath):
    locals = {}
    globals = {}
    try:
        exec(compile(open(filepath, "rb").read(),
                     filepath, 'exec'),
             globals,
             locals)
    except Exception as e:
        # any exception means full stop
        raise ValueError('webapp at {} is broken: {}'.format(
            filepath, exc_str(e)))
    if not len(locals) or 'DLWebApp' not in locals:
        raise ValueError(
            "loading webapp '%s' did not yield a 'DLWebApp' symbol, found: %s",
            filepath, locals.keys() if len(locals) else None)
    return locals['DLWebApp']


@build_doc
class WebApp(Interface):
    """
    """
    _params_ = dict(
        app=Parameter(
            args=('--app',),
            doc="yeah!",
            nargs='+',
            action='append'),
        dataset=Parameter(
            args=("-d", "--dataset"),
            doc="""specify the dataset to serve as the anchor of the webapp.
            An attempt is made to identify the dataset based on the current
            working directory. If a dataset is given, the command will be
            executed in the root directory of this dataset.""",
            constraints=EnsureDataset() | EnsureNone()),
        daemonize=Parameter(
            args=("--daemonize",),
            action='store_true',
            doc="yeah!"),
    )

    @staticmethod
    @datasetmethod(name='webapp')
    @eval_results
    def __call__(app, dataset=None, daemonize=False):
        apps = assure_list(app)
        if not apps:
            raise ValueError('no app specification given')
        if not isinstance(apps[0], (list, tuple)):
            apps = [apps]

        known_webapps = _get_webapps()
        import cherrypy

        # set the priority according to your needs if you are hooking something
        # else on the 'before_finalize' hook point.
        @cherrypy.tools.register('before_finalize', priority=60)
        def secureheaders():
            headers = cherrypy.response.headers
            headers['X-Frame-Options'] = 'DENY'
            headers['X-XSS-Protection'] = '1; mode=block'
            headers['Content-Security-Policy'] = "default-src='self'"
            # only add Strict-Transport headers if we're actually using SSL; see the ietf spec
            # "An HSTS Host MUST NOT include the STS header field in HTTP responses
            # conveyed over non-secure transport"
            # http://tools.ietf.org/html/draft-ietf-websec-strict-transport-sec-14#section-7.2
            if (cherrypy.server.ssl_certificate != None and
                    cherrypy.server.ssl_private_key != None):
                headers['Strict-Transport-Security'] = 'max-age=31536000'  # one year

        if daemonize:
            from cherrypy.process.plugins import Daemonizer
            Daemonizer(cherrypy.engine).subscribe()
            #PIDFile(cherrypy.engine, '/var/run/myapp.pid').subscribe()

        # when running on a priviledged port
        #DropPrivileges(cherrypy.engine, uid=1000, gid=1000).subscribe()

        for appspec in apps:
            label = appspec[0]
            mount = None
            if len(appspec) > 1:
                mount = appspec[1]
            else:
                mount = '/'
            appinfo = known_webapps[label]
            # get the webapp class
            cls = _import_webapp(opj(appinfo['directory'], 'app.py'))
            # fire up the webapp instance
            inst = cls(**dict(dataset=dataset))
            # mount under global URL tree (default or given suburl)
            app = cherrypy.tree.mount(
                root=inst,
                script_name=mount,
                # app config file, it is ok for that file to not exist
                config=opj(appinfo['directory'], 'app.conf')
            )
            # forcefully impose more secure mode
            # TODO might need one (or more) switch(es) to turn things off for
            # particular scenarios
            app.merge({
                '/': {
                    # turns all security headers on
                    'tools.secureheaders.on': True,
                    'tools.sessions.secure': True,
                    'tools.sessions.httponly': True}})
            static_dir = opj(appinfo['directory'], 'static')
            if isdir(static_dir):
                app.merge({
                    # the key has to be / even when an app is mount somewhere
                    # below
                    '/': {
                        'tools.staticdir.on': True,
                        'tools.staticdir.root': appinfo['directory'],
                        'tools.staticdir.dir': 'static'}}
                )
        cherrypy.engine.start()
        cherrypy.engine.block()
        yield {}
