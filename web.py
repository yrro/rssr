#!/usr/bin/python

import sys
import traceback
import urllib

import routes

m = routes.Mapper ()
m.connect ('', controller = 'root', action = 'view', conditions = {'method': ('GET', 'HEAD')})

class Http404 (Exception):
	'''Raise an instance of this to return a default 404 error.'''
	pass

def root ():
	return Response (['root'])

class Response (object):
	'''View functions should return an instance of this.
	
	data: an iterable of str instances.'''
	def __init__ (self, data):
		self.status = '200 OK'
		self.headers = [('content-type', 'text/plain')]
		self.data = data

class ResponseNotFound (Response):
	def __init__ (self, *args, **kwargs):
		super (ResponseNotFound, self).__init__ (*args, **kwargs)
		self.status = '404 Not Found'

def app (environ, start_response):
	'''A WSGI application.'''
	try:
		# The requested path. routes expects a utf-8 encoded str object.
		path_info = urllib.unquote (environ['PATH_INFO'])
		
		rconfig = routes.request_config ()
		rconfig.mapper = m # why?
		#rconfig.redirect = ?
		rconfig.environ = environ # means we dont' have to set the other properties

		try:
			route = m.match (path_info)
			if route == None:
				raise Http404 ()

			try:
				view = globals ()[route['controller']]
			except KeyError:
				raise Http404 ()

			r = view ()
			if not isinstance (r, Response):
				raise Exception ('Expected Response, got %s' % (type (r)))
		except Http404, e:
			r = ResponseNotFound ('not found\n')
		
		start_response (r.status, r.headers)
		return r.data
	except Exception, e:
		traceback.print_exc (file = environ['wsgi.errors'])
		start_response ('500 Internal Server Error', [('content-type', 'text/plain')], sys.exc_info ())
		return ('internal server error\n',)

if __name__ == '__main__':
	from paste import httpserver
	httpserver.serve (app, host='localhost', port='8000')
