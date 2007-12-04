#!/usr/bin/python

import cgitb
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
	return Response ('root')

class Response (object):
	'''View functions should return an instance of this.
	
	`data`: list of `str`s comprising the response.

	`headers`: mapping of response headers.'''
	def __init__ (self, data = ''):
		'''`data`: initial data to form the response; must be an `str`.'''
		self.status = '200 OK'

		self.__headers = [('content-type', 'text/plain')]
		self.headers = wsgiref.headers.Headers (self.__headers)

		self.data = []
		print >> self, data

	def write (self, data):
		if type (data) != str:
			raise Exception ('Tried to write non-string data to response')
		self.data.append (data)

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
				raise Exception ('Could not find controller "%s"' % (route['controller']))

			r = view ()
			if not isinstance (r, Response):
				raise Exception ('Expected Response, got %s' % (type (r)))
		except Http404, e:
			r = ResponseNotFound ('not found\n')
		
		start_response (r.status, r._Response__headers)
		return r.data
	except Exception, e:
		traceback.print_exc (file = environ['wsgi.errors'])

		#start_response ('500 Internal Server Error', [('content-type', 'text/plain')], sys.exc_info ())
		#return ['internal server error\n']

		from cStringIO import StringIO
		s = StringIO ()
		cgitb.Hook (file = s).handle ()
		s.seek (0)
		start_response ('500 Internal Server Error', [('content-type', 'text/html')], sys.exc_info ())
		return [s.read ()]

if __name__ == '__main__':
	import wsgiref
	from wsgiref.simple_server import make_server
	from wsgiref.validate import validator
	s = wsgiref.simple_server.make_server ('localhost', 8000, validator (app))
	try:
		s.serve_forever ()
	except KeyboardInterrupt, e:
		pass
