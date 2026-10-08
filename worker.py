from workers import wsgi
from app import app

entrypoint = wsgi.entrypoint(app)
