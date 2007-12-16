#!/usr/bin/python

import cgitb
import pdb
import sys
import traceback
import urlparse

from paste.httpexceptions import HTTPNotFound
from paste.wsgiwrappers import WSGIRequest, WSGIResponse
import routes
from wsgiref.headers import Headers

import db
import views

m = routes.Mapper (explicit = True)
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

class Response (object):
	'''View functions should return an instance of this.
	
	`data`: list of `str`s comprising the response.

	`headers`: mapping of response headers.'''
	def __init__ (self, data = None):
		'''`data`: initial data to form the response; must be an `str`.'''
		self.status = '200 OK'

		self.__headers = [('content-type', 'text/plain')]
		self.headers = Headers (self.__headers)

		self.data = []
		if data != None:
			print >> self, data

	def write (self, data):
		if type (data) != str:
			raise Exception ('Tried to write non-string data to response')
		self.data.append (data)

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
	import web
	if isinstance (result, web.Response):
		start_response (result.status, result._Response__headers)
		return result.data
	elif isinstance (result, WSGIResponse):
		return result (environ, start_response)

	if type (result) == type:
		t = result.__class__
	else:
		t = type (result)
	raise Exception ('Expected WSGIResponse or Response, got %s' % (t))

class cgitb_app:
	def __init__ (self, app):
		self.app = app
	
	def __call__ (self, environ, start_response):
		try:
			return self.app (environ, start_response)
		except Exception, e:
			traceback.print_exc (file = environ['wsgi.errors'])

			pdb.post_mortem (sys.exc_info ()[2])

			from cStringIO import StringIO
			s = StringIO ()
			cgitb.Hook (file = s).handle ()
			s.seek (0)
			start_response ('500 Internal Server Error', [('content-type', 'text/html')], sys.exc_info ())
			return s

if __name__ == '__main__':
	# Ensure that the app acts as a valid WSGI application
	#from wsgiref.validate import validator
	#app = validator (app)

	# Handle Paste HTTP exceptions
	from paste.httpexceptions import HTTPExceptionHandler
	app = HTTPExceptionHandler (app)

	# Catch exceptions, render a pretty stack trace to the response
	#app = cgitb_app (app)

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
