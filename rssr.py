#!/usr/bin/python

import datetime

import feedparser
from twisted.python.util import InsensitiveDict
import twisted.web.error

import config
import db
import webclient

def got_data (data, factory, feed):
    parsed = feedparser.parse (data)
    
    session = db.Session ()
    rh = InsensitiveDict (dict = factory.response_headers)
    feed.http_etag = rh.get ('ETag', [None])[0]
    feed.http_lastmodified = rh.get ('Last-Modified', [None])[0]
    feed.update_fields (parsed)
    session.save_or_update (feed)

    # maps entry ids to parsed entry dicts
    current_entries_parsed = dict ([(e.id, e) for e in parsed['entries'] if e.get ('id') != None])

    # remove obsolete entries
    cutoff = datetime.datetime.utcnow () - datetime.timedelta (days = config.article_retention)
    from sqlalchemy.sql import not_
    obsolete_entries = feed.entries.filter (db.Entry.inserted < cutoff).filter (not_ (db.Entry.id.in_ (current_entries_parsed.keys ())))
    for oe in obsolete_entries:
        log.msg ('deleting %s' % (oe))
        session.delete (oe)

    # update old entries
    old_entries = feed.entries.filter (db.Entry.id.in_ (current_entries_parsed.keys ()))
    for oe in old_entries:
        #log.msg ('updating %s' % (oe))
        oe.update_fields (current_entries_parsed.pop (oe.id))
        session.update (oe)
    
    # insert new entries
    for ne_parsed in current_entries_parsed.values ():
        ne = db.Entry ()
        ne.feed = feed
        ne.read = False
        ne.inserted = datetime.datetime.utcnow ()
        ne.update_fields (ne_parsed)
        log.msg ('new entry %s' % (ne))
        feed.entries.append (ne)
    session.update (feed)

    session.commit ()

def got_error (failure, feed):
    if failure.check (twisted.web.error.Error):
        if failure.value.args[0] == '304':
            # the feed has not been modified--not an error
            return

    msg = '%s.%s' % (failure.type.__module__, failure.type.__name__)
    em = failure.getErrorMessage ()
    if len (em) > 0:
        msg = '%s: %s' % (msg, em)

    log.err ('%s: %s' % (feed, msg))
    
    session = db.Session ()
    session.rollback () # why didn't we get a new transaction?
    feed = session.query (db.Feed).get (feed.id) # feed may still be owned by got_data's session
    feed.error = msg
    session.save_or_update (feed)
    session.commit ()

    return failure

def refresh_feeds ():
    session = db.Session ()
    for feed in session.query (db.Feed):
        headers = {}
        if feed.http_etag != None:
            headers['If-None-Match'] = feed.http_etag
        if feed.http_lastmodified != None:
            headers['If-Modified-Since'] = feed.http_lastmodified
        factory = webclient.getPage (feed.href, timeout = 60, agent = 'rssr', headers = headers)
        session.expunge (feed)
        factory.deferred.addCallback (got_data, factory, feed)
        factory.deferred.addErrback (got_error, feed)

from twisted.python import log

if __name__ == '__main__':
    import sys
    log.startLogging (sys.stdout, setStdout=False)

    from twisted.internet import task
    l = task.LoopingCall (refresh_feeds)
    l.start (config.refresh_interval)

    from twisted.internet import reactor
    reactor.run ()

# vim: softtabstop=4 expandtab
