

class DLWebApp(object):
    import cherrypy
    from cherrypy import tools

    def __init__(self, dataset):
        from datalad.distribution.dataset import require_dataset
        self.ds = require_dataset(
            dataset, check_installed=True, purpose='serving')

    @cherrypy.expose
    def index(self):
        return """<html>
          <head></head>
          <body>
            <form method="get" action="m">
              <input type="text" placeholder="relative path" name="path" />
              <button type="submit">Give me metadata!</button>
            </form>
          </body>
        </html>"""

    @cherrypy.expose
    @tools.json_out()
    def m(self, path):
        from datalad.api import metadata
        return metadata(path, dataset=self.ds, result_renderer='disabled')

    @tools.json_out()
    @cherrypy.expose
    def config(self):
        import cherrypy
        return cherrypy.request.app.config
