import elementtree.ElementTree as et
from paste.httpexceptions import HTTPNotFound, HTTPFound
from paste.wsgiwrappers import WSGIResponse
import pytz
from sqlalchemy import sql

import db
import web

from xml.dom import XHTML_NAMESPACE

def list_feeds (request):
	s = db.Session ()

	res = WSGIResponse ()
	return res

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
	raise HTTPFound (web.url_for_view ('view_feed', **kwargs))

def view_feed (request, feed_id = None):
	# TODO: TZ environment variable (if feasable)
	tz = pytz.tzfile.build_tzinfo ('local', open ('/etc/localtime', 'rb'))
	
	ht = et.Element ('html')
	ht.set ('xmlns', XHTML_NAMESPACE)

	he = et.Element ('head')
	ht.append (he)

	t = et.Element ('title')
	t.text = 'rssr'
	he.append (t)

	bo = et.Element ('body')
	ht.append (bo)

	s = db.Session ()
	date_clause = sql.func.coalesce (db.Entry.updated, db.Entry.published, db.Entry.created, db.Entry.inserted)
	q = s.query (db.Entry).add_column (date_clause)
	if feed_id != None:
		feed = s.query (db.Feed).get (feed_id)
		if feed == None:
			raise HTTPNotFound ()
		q = q.filter_by (feed = feed)
	if request.GET.get ('show_all', 'no') == 'no':
		q = q.filter_by (read = False)
	q = q.order_by (date_clause)[0:20]

	h1 = et.Element ('h1')
	if feed_id != None:
		h1.text = feed.title.as_text ()
	else:
		h1.text = 'all feeds'
	bo.append (h1)

	form = et.Element ('form')
	form.set ('method', 'GET')
	p = et.Element ('p')
	b = et.Element ('button')
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
		div = et.Element ('div')
		div.set ('class', 'entry')
		div.set ('style', 'border-left: 1px solid #ccc; padding-left: 0.5em;')
		bo.append (div)

		h1 = et.Element ('h2')
		if entry.link != None:
			h1a = et.Element ('a')
			h1a.set ('href', entry.link)
			h1a.text = entry.get_title ()
			h1.append (h1a)
		else:
			h1.text = entry.get_title ()
		div.append (h1)

		p = et.Element ('p')
		p.text = '(%i) Posted to %s on %s' % (entry.id, entry.feed.get_title (), date.replace (tzinfo = pytz.utc).astimezone (tz).strftime ('%Y-%m-%d %H:%M %Z (%z)'))
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

		elems = content_tree.find ('body')
		if elems.text == None and len (elems) == 0:
			raise Exception ('no elements in entry #%i' % (entry.id))

		# handle the body element's first text node
		di = et.Element ('div')
		di.text = elems.text
		div.append (di)

		# subsequent text nodes are considered a part of the contained elements
		for elem in elems:
			di.append (elem)
	
	bo.append (et.Element ('hr'))

	fo = et.Element ('form')
	fo.set ('method', 'POST')
	kwargs = {}
	if feed_id != None:
		kwargs['feed_id'] = feed_id
	fo.set ('action', web.url_for_view ('mark_read', **kwargs))
	bo.append (fo)

	for e, d in q:
		ids = et.Element ('input')
		ids.set ('name', 'ids')
		ids.set ('type', 'hidden')
		ids.set ('value', str (e.id))
		fo.append (ids)

	sb = et.Element ('button')
	sb.set ('type', 'submit')
	sb.text = 'Mark all read'
	fo.append (sb)

	r = WSGIResponse ()
	r.headers['content-type'] = 'application/xhtml+xml; charset=utf-8'
	print >> r, '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">'
	
	t = et.ElementTree (ht)
	t.write (r, 'utf-8')

	return r


