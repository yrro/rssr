#!/usr/bin/python

import cgi
import cgitb
import sys
import traceback
import urllib
import urlparse

import routes
from sqlalchemy import sql

import db

m = routes.Mapper ()
m.connect ('', controller = 'root', conditions = {'method': ('GET', 'HEAD')})
m.connect ('mark_read', controller = 'mark_read', conditions = {'method': ('POST',)})

class Http404 (Exception):
	'''Raise an instance of this to return a default 404 error.'''
	pass

def mark_read (request):
	if request.environ['CONTENT_TYPE'] != 'application/x-www-form-urlencoded':
		raise Exception ('wrong form data encoding')
	data = request.environ['wsgi.input'].read (int (request.environ['CONTENT_LENGTH']))
	e_ids = cgi.parse_qs (data)['ids']

	s = db.Session ()
	entries = s.query (db.Entry).filter (db.Entry.id.in_ (e_ids))
	for entry in entries:
		entry.read = True
		s.update (entry)
	s.commit ()

	return ResponseRedirect (get_absolute_url (request, routes.util.url_for (controller = 'root')))

def root (request):
	import elementtree.ElementTree as et
	
	ht = et.Element ('{http://www.w3.org/1999/xhtml}html')

	he = et.Element ('{http://www.w3.org/1999/xhtml}head')
	ht.append (he)

	t = et.Element ('{http://www.w3.org/1999/xhtml}title')
	t.text = 'rssr'
	he.append (t)

	bo = et.Element ('{http://www.w3.org/1999/xhtml}body')
	ht.append (bo)

	s = db.Session ()
	date_clause = sql.func.coalesce (db.Entry.updated, db.Entry.published, db.Entry.created, db.Entry.inserted)
	q = s.query (db.Entry).add_column (date_clause).filter_by (read = False).order_by (date_clause)[0:20]
	for entry, date in q:
		h1 = et.Element ('{http://www.w3.org/1999/xhtml}h1')
		if entry.link != None:
			h1a = et.Element ('{http://www.w3.org/1999/xhtml}a')
			h1a.set ('href', entry.link)
			h1a.text = entry.get_title ()
			h1.append (h1a)
		else:
			h1.text = entry.get_title ()
		bo.append (h1)

		p = et.Element ('{http://www.w3.org/1999/xhtml}p')
		p.text = '(%i) Posted to %s on %s' % (entry.id, entry.feed.title.as_text (), date)
		if entry.author != None and entry.author != '':
			p.text = '%s by %s' % (p.text, entry.author)
		bo.append (p)

		#if entry.id == 1841: import pdb; pdb.set_trace ()
		#if entry.id == 3209: import pdb; pdb.set_trace ()
		body = entry.get_body ().as_html ()
		def parse_unicode (document):
			from cStringIO import StringIO
			from elementtidy import TidyHTMLTreeBuilder
			return et.parse (StringIO (body.encode ('utf-8')), TidyHTMLTreeBuilder.TreeBuilder (encoding = 'utf-8'))
		content_tree = parse_unicode (body)

		elems = content_tree.find ('{http://www.w3.org/1999/xhtml}body')
		if elems.text == None and len (elems) == 0:
			raise Exception ('no elements in entry #%i' % (entry.id))

		# handle the body element's first text node
		di = et.Element ('{http://www.w3.org/1999/xhtml}div')
		di.text = elems.text
		bo.append (di)

		# subsequent text nodes are considered a part of the contained elements
		for elem in elems:
			di.append (elem)
	
	bo.append (et.Element ('{http://www.w3.org/1999/xhtml}hr'))

	fo = et.Element ('{http://www.w3.org/1999/xhtml}form')
	fo.set ('method', 'POST')
	fo.set ('action', routes.util.url_for (controller = 'mark_read'))
	bo.append (fo)

	for e, d in q:
		ids = et.Element ('{http://www.w3.org/1999/xhtml}input')
		ids.set ('name', 'ids')
		ids.set ('type', 'hidden')
		ids.set ('value', str (e.id))
		fo.append (ids)

	sb = et.Element ('{http://www.w3.org/1999/xhtml}button')
	sb.set ('type', 'submit')
	sb.text = 'Mark all read'
	fo.append (sb)

	r = Response ()
	r.headers['content-type'] = 'application/xhtml+xml'
	print >> r, '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">'
	
	t = et.ElementTree (ht)
	t.write (r, 'utf-8')

	return r

def get_absolute_url (request, path):
	scheme = request.environ['wsgi.url_scheme']
	
	if request.environ.get ('HTTP_HOST'):
		host = request.environ['HTTP_HOST']
	else:
		host = request.environ['SERVER_NAME']
		if (scheme == 'http' and request.environ['SERVER_PORT'] != 80) or (scheme == 'https' and request.environ['SERVER_PORT'] != 443):
			host = '%s:%s' % (host, request.environ['SERVER_PORT'])

	return urlparse.urljoin (urlparse.urlunsplit ((scheme, host, '', '', '')), path)


class Request (object):
	def __init__ (self, environ):
		self.environ = environ

class Response (object):
	'''View functions should return an instance of this.
	
	`data`: list of `str`s comprising the response.

	`headers`: mapping of response headers.'''
	def __init__ (self, data = None):
		'''`data`: initial data to form the response; must be an `str`.'''
		self.status = '200 OK'

		self.__headers = [('content-type', 'text/plain')]
		self.headers = wsgiref.headers.Headers (self.__headers)

		self.data = []
		if data != None:
			print >> self, data

	def write (self, data):
		if type (data) != str:
			raise Exception ('Tried to write non-string data to response')
		self.data.append (data)

class ResponseNotFound (Response):
	def __init__ (self, *args, **kwargs):
		super (ResponseNotFound, self).__init__ (*args, **kwargs)
		self.status = '404 Not Found'

class ResponseRedirect (Response):
	def __init__ (self, url):
		super (ResponseRedirect, self).__init__ ()
		self.status = '302 Found'

		if urlparse.urlsplit (url)[0] == '':
			raise Exception ('Attempted to redirect to a non-absolute URL')
		self.headers['location'] = url

def app (environ, start_response):
	'''A WSGI application.'''
	try:
		request = Request (environ)
		# The requested path. routes expects a utf-8 encoded str object.
		url = urllib.unquote (environ['PATH_INFO'][len (environ['SCRIPT_NAME']):])
		
		rconfig = routes.request_config ()
		rconfig.mapper = m # why?
		#rconfig.redirect = ?
		rconfig.environ = environ # means we dont' have to set the other properties

		try:
			route = m.match (url)
			if route == None:
				raise Http404 ()

			try:
				view = globals ()[route['controller']]
			except KeyError:
				raise Exception ('Could not find controller "%s"' % (route['controller']))

			r = view (request)
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
