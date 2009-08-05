#!/usr/bin/python

import sys
import xml.dom.minidom

import db

d = xml.dom.minidom.parse (sys.argv[1])

opml = d.firstChild
if opml.tagName != 'opml':
	raise Exception ('not an OPML document')

body = None
for n in opml.childNodes:
	if n.tagName == 'body':
		body = n
		break
if body == None:
	raise Exception ('no body element')

outlines = [n for n in body.childNodes if n.nodeType == xml.dom.minidom.Node.ELEMENT_NODE and n.tagName == 'outline']

s = db.Session ()
for o in outlines:
	f = db.Feed (o.getAttribute ('xmlUrl'))
	s.save (f)
s.commit ()

# vim: noet sts=0
