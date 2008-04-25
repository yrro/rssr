#!/usr/bin/python

from paste.httpexceptions import HTTPNotFound
from paste.wsgiwrappers import WSGIRequest, WSGIResponse
import routes

import db
import views

m = routes.Mapper (explicit = True)
m.connect ('', controller = 'root', conditions = {'method': ('GET', 'HEAD')})
m.connect ('view',           controller = 'view_feed', conditions = {'method': ('GET', 'HEAD')})
m.connect ('view/mark_read', controller = 'mark_read', conditions = {'method': ('POST',)})
m.connect ('view/:feed_id', controller = 'view_feed', conditions = {'method': ('GET', 'HEAD')})
m.connect ('view/:feed_id/mark_read', controller = 'mark_read', conditions = {'method': ('POST',)})

def url_for_view (view_name, **kwargs):
	'''Given a view name and (optional) parameters, return the URL to access that view.'''
	url = routes.util.url_for (controller = view_name, **kwargs)
	if url == None:
		raise Exception ('No URL found for controller "%s" {%s}' % (controller, kwargs))
	return url

def app (environ, start_response):
	'''Route the request to an appropriate view function.'''
	routing_args = environ['wsgiorg.routing_args'][1]
	try:
		view_name = routing_args.pop ('controller')
	except KeyError:
		raise HTTPNotFound ()

	try:
		view = getattr (views, view_name)
	except AttributeError:
		raise Exception ('Could not find view "%s"' % (view_name))

	result = view (WSGIRequest (environ), **routing_args)
	assert (isinstance (result, WSGIResponse))
	return result (environ, start_response)

if __name__ == '__main__':
	# Ensure that the app acts as a valid WSGI application
	#from wsgiref.validate import validator
	#app = validator (app)

	# Handle Paste HTTP exceptions
	from paste.httpexceptions import HTTPExceptionHandler
	app = HTTPExceptionHandler (app)

	# Paste's version of the above
	#from paste.exceptions.errormiddleware import ErrorMiddleware
	#app = ErrorMiddleware (app, debug = True)

	# Interactive debugger
	from paste.evalexception.middleware import EvalException
	app = EvalException (app)

	# Parse URLs, placing an entry in the environment that
	# lets us work out which view function to call
	from routes.middleware import RoutesMiddleware
	app = RoutesMiddleware (app, m)

	# Host the application in an HTTP server
	from wsgiref.simple_server import make_server
	s = make_server ('localhost', 8000, app)
	try:
		s.serve_forever ()
	except KeyboardInterrupt, e:
		pass
