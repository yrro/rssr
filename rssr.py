#!/usr/bin/python

import datetime

import feedparser
from sqlalchemy import sql
from twisted.internet import defer

import config
import db
import util

def handle_error (failure, feed):
    msg = '%s.%s' % (failure.type.__module__, failure.type.__name__)
    em = failure.getErrorMessage ()
    if len (em) > 0:
        msg = '%s: %s' % (msg, em)

    log.err ('%s: %s' % (feed, msg))

    session = db.Session ()
    try:
        feed = session.query (db.Feed).get (feed.id) # feed may still be owned by got_data's session
        feed.error = failure.getErrorMessage ()
        session.update (feed)
        session.commit ()
    finally:
        session.close ()

def save_feed (parsed, feed):
    log.msg ('%s: saving %i entries...' % (feed, len (parsed.entries)))
 
    session = db.Session ()
    try:
        feed.update_fields (parsed)
        session.save_or_update (feed)

        # maps entry GUIDs to feed's parsed entries
        current_entries_parsed = dict ((util.feedparser_entry_guid (e), e) for e in parsed['entries'])

        # remove obsolete entries -- those that are NOT still in the feed data, and
        # that are older than a certain age
        cutoff = datetime.datetime.utcnow () - datetime.timedelta (days = config.article_retention)
        obsolete_entries = feed.entries.filter (db.Entry.inserted < cutoff).filter (sql.not_ (db.Entry.guid.in_ (current_entries_parsed.keys ())))
        for oe in obsolete_entries:
            log.msg ('deleting %s' % (oe))
            session.delete (oe)

        # update old entries -- those that we already saved in a previous run,
        # but that might have updated properties. as entries are processed,
        # they are removed from current_entries_parsed.
        old_entries = feed.entries.filter (db.Entry.guid.in_ (current_entries_parsed.keys ()))
        for oe in old_entries:
            oe.update_fields (current_entries_parsed.pop (oe.guid))
            session.update (oe)

        # insert new entries -- anything left in current_entries_parsed
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
    finally:
        session.close ()
    log.msg ('...done')

def parse_feed (x, data, feed):
    log.msg ('%s: parsing' % (feed))
    parsed = feedparser.parse (data)
    return parsed

def group_done (*args):
    global pending_groups
    pending_groups -= 1
    log.msg ('group done, %i remain' % (pending_groups))

    if pending_groups == 0:
        # Returning a Deferred will cause the callbacks to be
        # added to the last group's Deferred's actions.
        d = defer.succeed (None)
        while len (downloaded_feeds) > 0:
            feed, data = downloaded_feeds.pop ()
            d.addCallback (parse_feed, data, feed)
            d.addCallback (save_feed, feed)
            d.addErrback (handle_error, feed)
        return d

def store_feed (data, feed):
    log.msg ('%s: storing' % (feed))
    downloaded_feeds.append ((feed, data))

def download_feed (x, feed):
    log.msg ('%s: downloading' % (feed))
    from twisted.web import client
    return client.getPage (feed.href, timeout = config.feed_fetch_timeout, agent = 'rssr')

downloaded_feeds = []
pending_groups = 0

def refresh_feeds ():
    session = db.Session ()
    try:
        feeds = session.query (db.Feed).order_by (sql.func.random ())

        global pending_groups
        groups = [[] for f in xrange (config.deferred_groups)]
        pending_groups = len (groups)

        for i, feed in enumerate (feeds):
            session.expunge (feed)
            groups[i % config.deferred_groups].append (feed)

        for g in groups:
            # This Deferred will call each callback as soon as it is added.
            # <http://twistedmatrix.com/documents/current/api/twisted.internet.defer.html#succeed>
            # The argument is passed to the first callback added.
            d = defer.succeed (None)
            for feed in g:
                # download_feed returns a deferred, which causes d's callback
                # chain to wait for the returned callback chain to be processed.
                # <http://twistedmatrix.com/projects/core/documentation/howto/defer.html#auto11>.
                d.addCallback (download_feed, feed)
                #d.addErrback (handle_403) # but if we handle a 403, what do we return? whatever we do will go to parse_feed

                d.addCallback (store_feed, feed)

                # Finally, this errback traps any failures from this feed
                # so that the deferred can continue to process the next
                # feed.
                d.addErrback (handle_error, feed)

            # The last time group_done is called, it will return a Deferred
            # that will cause feeds to be parsed and stored.
            d.addCallback (group_done)
    finally:
        session.close ()

from twisted.python import log

if __name__ == '__main__':
    import sys
    log.startLogging (sys.stdout, setStdout=False)

    from twisted.internet import task
    l = task.LoopingCall (refresh_feeds)
    l.start (config.refresh_interval)

    from twisted.internet import reactor
    reactor.run ()

# vim: sts=4 et
