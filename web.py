#!/usr/bin/python

import cgi
import cgitb
import sys
import traceback
import urllib
import urlparse

from paste.httpexceptions import HTTPNotFound, HTTPFound
from paste.wsgiwrappers import WSGIRequest
import pytz
import routes, routes.middleware
from sqlalchemy import sql
from wsgiref.headers import Headers

import db

m = routes.Mapper ()
m.connect ('view',           controller = 'view_feed', conditions = {'method': ('GET', 'HEAD')})
m.connect ('view/mark_read', controller = 'mark_read', conditions = {'method': ('POST',)})
m.connect ('view/:feed_id', controller = 'view_feed', conditions = {'method': ('GET', 'HEAD')})
m.connect ('view/:feed_id/mark_read', controller = 'mark_read', conditions = {'method': ('POST',)})

def url_for_controller (controller, **kwargs):
	url = routes.util.url_for (controller = controller, **kwargs)
	if url == None:
		raise Exception ('No URL found for controller "%s" {%s}' % (controller, kwargs))
	return url

def mark_read (request, feed_id = None):
	s = db.Session ()
	entries = s.query (db.Entry).filter (db.Entry.id.in_ (request.POST.getall ('ids')))
	for entry in entries:
		entry.read = True
		s.update (entry)
	s.commit ()

	kwargs = {}
	if feed_id != None:
		kwargs['feed_id'] = feed_id
	raise HTTPFound (url_for_controller ('view_feed', **kwargs))

def view_feed (request, feed_id = None):
	import elementtree.ElementTree as et

	# TODO: TZ environment variable (if feasable)
	tz = pytz.tzfile.build_tzinfo ('local', open ('/etc/localtime', 'rb'))
	
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
	#q = s.query (db.Entry).add_column (date_clause).filter_by (read = False).order_by (date_clause)[0:20]
	q = s.query (db.Entry).add_column (date_clause)
	if feed_id != None:
		feed = s.query (db.Feed).get (feed_id)
		if feed == None:
			raise HTTPNotFound ()
		q = q.filter_by (feed = feed)
	if request.GET.get ('show_all', 'no') == 'no':
		q = q.filter_by (read = False)
	q = q.order_by (date_clause)[0:20]

	h1 = et.Element ('{http://www.w3.org/1999/xhtml}h1')
	if feed_id != None:
		h1.text = feed.title.as_text ()
	else:
		h1.text = 'all feeds'
	bo.append (h1)

	form = et.Element ('{http://www.w3.org/1999/xhtml}form')
	form.set ('method', 'GET')
	p = et.Element ('{http://www.w3.org/1999/xhtml}p')
	b = et.Element ('{http://www.w3.org/1999/xhtml}button')
	b.set ('name', 'show_all')
	if request.GET.get ('show_all', 'no') == 'no':
		p.text = 'showing unread entries'
		b.text = 'show all'
		b.set ('value', 'yes')
	else:
		p.text = 'showing all entries'
		b.text = 'show unread'
		b.set ('value', 'no')
	p.append (b)
	form.append (p)
	bo.append (form)

	for entry, date in q:
		div = et.Element ('{http://www.w3.org/1999/xhtml}div')
		div.set ('class', 'entry')
		div.set ('style', 'border-left: 1px solid #ccc; padding-left: 0.5em;')
		bo.append (div)

		h1 = et.Element ('{http://www.w3.org/1999/xhtml}h2')
		if entry.link != None:
			h1a = et.Element ('{http://www.w3.org/1999/xhtml}a')
			h1a.set ('href', entry.link)
			h1a.text = entry.get_title ()
			h1.append (h1a)
		else:
			h1.text = entry.get_title ()
		div.append (h1)

		p = et.Element ('{http://www.w3.org/1999/xhtml}p')
		p.text = '(%i) Posted to %s on %s' % (entry.id, entry.feed.title.as_text (), date.replace (tzinfo = pytz.utc).astimezone (tz).strftime ('%Y-%m-%d %H:%M %Z (%z)'))
		if entry.author != None and entry.author != '':
			p.text = '%s by %s' % (p.text, entry.author)
		div.append (p)

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
		div.append (di)

		# subsequent text nodes are considered a part of the contained elements
		for elem in elems:
			di.append (elem)
	
	bo.append (et.Element ('{http://www.w3.org/1999/xhtml}hr'))

	fo = et.Element ('{http://www.w3.org/1999/xhtml}form')
	fo.set ('method', 'POST')
	fo.set ('action', url_for_controller ('mark_read')) # how does this work when feed_id != None?
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

class ResponseRedirect (Response):
	def __init__ (self, url):
		super (ResponseRedirect, self).__init__ ()
		self.status = '302 Found'

		if urlparse.urlsplit (url)[0] == '':
			raise Exception ('Attempted to redirect to a non-absolute URL')
		self.headers['location'] = url

def app (environ, start_response):
	'''Route the request to an appropriate view function.'''
	routing_args = environ['wsgiorg.routing_args'][1]
	try:
		controller = routing_args.pop ('controller')
	except KeyError:
		raise HTTPNotFound ()

	try:
		view = globals ()[controller]
	except KeyError:
		raise Exception ('Could not find controller "%s"' % (route['controller']))

	routing_args.pop ('action') # we don't use this
	result = view (WSGIRequest (environ), **routing_args)
	if not isinstance (result, Response):
		raise Exception ('Expected Response, got %s' % (type (response)))
	
	start_response (result.status, result._Response__headers)
	return result.data

class cgitb_app:
	def __init__ (self, app):
		self.app = app
	
	def __call__ (self, environ, start_response):
		try:
			return self.app (environ, start_response)
		except Exception, e:
			traceback.print_exc (file = environ['wsgi.errors'])

			import pdb
			pdb.post_mortem (sys.exc_info ()[2])

			from cStringIO import StringIO
			s = StringIO ()
			cgitb.Hook (file = s).handle ()
			s.seek (0)
			start_response ('500 Internal Server Error', [('content-type', 'text/html')], sys.exc_info ())
			return s

if __name__ == '__main__':
	# Ensure that the app acts as a valid WSGI application
	from wsgiref.validate import validator
	app = validator (app)

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
