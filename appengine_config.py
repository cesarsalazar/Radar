from gaesessions import SessionMiddleware
from google.appengine.ext.appstats import recording
import keys                    

def webapp_add_wsgi_middleware(app):
    app = SessionMiddleware(app, cookie_key=keys.cookie_key)
    app = recording.appstats_wsgi_middleware(app)
    return app                 
