import xml.etree.ElementTree as et
from paste.httpexceptions import HTTPNotFound, HTTPFound
from paste.wsgiwrappers import WSGIResponse
import pytz
from sqlalchemy import sql
import urllib
import urlparse

import db
import web

from xml.dom import XHTML_NAMESPACE
ET_XHTML_NAMESPACE = '{%s}' % (XHTML_NAMESPACE)

def root (request):
	raise HTTPFound (web.url_for_view ('view_feed'))

@db.with_session
def list_feeds (session, request):
	res = WSGIResponse ()
	print >> res, u'unicode \u1234 text!'
	return res

@db.with_session
def mark_read (session, request, feed_id = None):
	entries = session.query (db.Entry).filter (db.Entry.id.in_ (request.POST.getall ('ids')))
	for entry in entries:
		entry.read = True
		session.update (entry)
	session.commit ()

	kwargs = {}
	if feed_id != None:
		kwargs['feed_id'] = feed_id
	raise HTTPFound (web.url_for_view ('view_feed', **kwargs))

@db.with_session
def view_feed (session, request, feed_id = None):
	# TODO: TZ environment variable (if feasable)
	try:
		tz = pytz.tzfile.build_tzinfo ('local', open ('/etc/localtime', 'rb'))
	except:
		tz = pytz.utc

	ht = et.Element ('html', xmlns = XHTML_NAMESPACE)

	he = et.SubElement (ht, 'head')

	t = et.SubElement (he, 'title')
	t.text = 'rssr'

	bo = et.SubElement (ht, 'body')

	date_clause = sql.func.coalesce (db.Entry.updated, db.Entry.published, db.Entry.created, db.Entry.inserted)
	q = session.query (db.Entry).add_column (date_clause)
	if feed_id != None:
		feed = session.query (db.Feed).get (feed_id)
		if feed == None:
			raise HTTPNotFound ()
		q = q.filter_by (feed = feed)
	if request.GET.get ('show_all', 'no') == 'no':
		q = q.filter_by (read = False)
	q = q.order_by (date_clause)[0:20]

	h1 = et.SubElement (bo, 'h1')
	h1.text = 'view entries'

	p = et.SubElement (bo, 'p')
	if feed_id != None:
		p.text = 'from '
		st = et.SubElement (p, 'strong')
		st.text = feed.title.as_text ()
		st.tail = ' '
		a = et.SubElement (p, 'a')
		a.text = '(view from all)'
		a.tail = ' '
		a.set ('href', web.url_for_view ('view_feed'))
	else:
		p.text = 'from all feeds '

	a = et.SubElement (p, 'a')
	a.text = '(list all)'
	a.set ('href', web.url_for_view ('list_feeds'))

	if session.query (db.Feed).filter (db.Feed.error != None).count () > 0:
		a.tail = ' '
		a = et.SubElement (p, 'a')
		a.text = '(list broken)'
		a.set ('href', 'blah')

	p = et.SubElement (bo, 'p')
	a = et.SubElement (p, 'a')
	kwargs = {}
	if feed_id != None:
		kwargs['feed_id'] = feed_id
	url = list (urlparse.urlsplit (web.url_for_view ('view_feed', **kwargs)))
	if request.GET.get ('show_all', 'no') == 'no':
		p.text = 'showing unread entries '
		a.text = '(show all)'
		url[3] = urllib.urlencode ({'show_all': 'yes'})
	else:
		p.text = 'showing all entries '
		a.text = '(show only unread)'
		url[3] = urllib.urlencode ({'show_all': 'no'})
	a.set ('href', urlparse.urlunsplit (url))

	for entry, date in q:
		div = et.SubElement (bo, 'div')
		div.set ('class', 'entry')
		div.set ('style', 'border-left: 1px solid #ccc; padding-left: 0.5em;')

		h1 = et.SubElement (div, 'h2')
		if entry.link != None:
			h1a = et.SubElement (h1, 'a')
			h1a.set ('href', entry.link)
			h1a.text = entry.get_title ()
		else:
			h1.text = entry.get_title ()

		p = et.SubElement (div, 'p')
		p.text = '(%i) posted to ' % (entry.id)
		a = et.SubElement (p, 'a')
		a.text = entry.feed.get_title ()
		a.set ('href', web.url_for_view ('view_feed', feed_id = entry.feed.id))
		a.tail = ' on %s' % (date.replace (tzinfo = pytz.utc).astimezone (tz).strftime ('%Y-%m-%d %H:%M %Z (%z)'))
		if entry.author != None and entry.author != '':
			a.tail += ' by %s' % (entry.author)

		#if entry.id == 1841: import pdb; pdb.set_trace ()
		#if entry.id == 3209: import pdb; pdb.set_trace ()
		body = entry.get_body ().as_html ()
		def parse_unicode (document):
			from cStringIO import StringIO
			from elementtidy import TidyHTMLTreeBuilder
			from xml.parsers.expat import ExpatError
			try:
				return et.parse (StringIO (body.encode ('utf-8')), TidyHTMLTreeBuilder.TreeBuilder (encoding = 'utf-8'))
			except ExpatError, e:
				return et.parse (StringIO ('''<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN"
					"http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">
					<html xmlns="http://www.w3.org/1999/xhtml">
					<body><em>Error parsing body</em></body>
					</html>'''))
		body_tree = parse_unicode (body)

		elems = body_tree.find (ET_XHTML_NAMESPACE + 'body') # TODO: xpath
		if elems == None:
			raise Exception ('no <html:body> element for entry #%i' % (entry.id))
		elif elems.text == None and len (elems) == 0:
			raise Exception ('empty <html:body> element for entry #%i' % (entry.id))

		# handle the body element's first text node
		di = et.SubElement (div, 'div')
		di.text = elems.text
		# subsequent text nodes are considered a part of the contained elements

		# strip XHTML namespace from elements
		for elem in elems.getiterator ():
			if elem.tag.startswith (ET_XHTML_NAMESPACE):
				elem.tag = elem.tag[len (ET_XHTML_NAMESPACE):]

		for elem in elems:
			di.append (elem)

	et.SubElement (bo, 'hr')

	fo = et.SubElement (bo, 'form', method='post')
	kwargs = {}
	if feed_id != None:
		kwargs['feed_id'] = feed_id
	fo.set ('action', web.url_for_view ('mark_read', **kwargs))

	p = et.SubElement (fo, 'p')
	for e, d in q:
		ids = et.SubElement (p, 'input')
		ids.set ('name', 'ids')
		ids.set ('type', 'hidden')
		ids.set ('value', str (e.id))

	sb = et.SubElement (p, 'button')
	sb.set ('type', 'submit')
	sb.text = 'Mark all read'

	r = WSGIResponse ()
	r.headers['content-type'] = 'application/xhtml+xml; charset=utf-8'
	print >> r, '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">'

	t = et.ElementTree (ht)
	t.write (r, 'utf-8')

	return r

# vim: noet sts=0
