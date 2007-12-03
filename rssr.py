#!/usr/bin/python

import datetime

import feedparser

import config
import db

def handle_error (failure, feed):
    msg = '%s.%s' % (failure.type.__module__, failure.type.__name__)
    em = failure.getErrorMessage ()
    if len (em) > 0:
        msg = '%s: %s' % (msg, em)

    log.err ('%s: %s' % (feed, msg))

    session = db.Session ()
    feed = session.query (db.Feed).get (feed.id) # feed may still be owned by got_data's session
    feed.error = msg
    session.update (feed)
    session.commit ()

def done (*args):
    log.msg ('group done!')

def save_feed (parsed, feed):
    log.msg ('%s: saving %i entries...' % (feed, len (parsed.entries)))
 
    session = db.Session ()
    feed.update_fields (parsed)
    session.save_or_update (feed)

    # maps entry GUIDs to feed's parsed entries
    current_entries_parsed = dict ([(e.guid, e) for e in parsed['entries'] if e.get ('guid') != None])

    # remove obsolete entries -- those that are NOT still in the feed data, and
    # that are older than a certain age
    cutoff = datetime.datetime.utcnow () - datetime.timedelta (days = config.article_retention)
    from sqlalchemy.sql import not_
    obsolete_entries = feed.entries.filter (db.Entry.inserted < cutoff).filter (not_ (db.Entry.guid.in_ (current_entries_parsed.keys ())))
    for oe in obsolete_entries:
        #log.msg ('deleting %s' % (oe))
        session.delete (oe)

    # update old entries -- those that we already saved in a previous run,
    # but that might have updated properties. as entries are processed,
    # they are removed from current_entries_parsed.
    old_entries = feed.entries.filter (db.Entry.guid.in_ (current_entries_parsed.keys ()))
    for oe in old_entries:
        oe_parsed = current_entries_parsed.pop (oe.guid)
    
        # if updated date increases (or stops or starts being NULL) or
        # the title changes, update the field
        # TODO: move to Feed class
        #import util
        #oe_parsed_updated = util.struct_time_to_datetime (oe_parsed.get ('updated_parsed'))
        #if oe_parsed.has_key ('title_detail'):
        #    oe_parsed_title = db.MaybeHTML (oe_parsed['title_detail']['value'], oe_parsed['title_detail']['type'])
        #else:
        #    oe_parsed_title = None
        #if (oe.updated == None) != (oe_parsed_updated == None) \
        #        or oe_parsed_updated > oe.updated \
        #        or oe_parsed_title != oe.title:
        #    log.msg ('updating %s' % (oe))
        #    oe.update_fields (current_entries_parsed.pop (oe.guid))
        #    session.update (oe)
        oe.update_fields (oe_parsed)
        session.update (oe)
    
    # insert new entries -- anything left in current_entries_parsed
    for ne_parsed in current_entries_parsed.values ():
        ne = db.Entry ()
        ne.feed = feed
        ne.read = False
        ne.inserted = datetime.datetime.utcnow ()
        ne.update_fields (ne_parsed)
        #log.msg ('new entry %s' % (ne))
        feed.entries.append (ne)
    session.update (feed)

    session.commit ()
    log.msg ('...done')

def parse_feed (data, feed):
    log.msg ('%s: parsing' % (feed))
    parsed = feedparser.parse (data)
    return parsed

def download_feed (x, feed):
    log.msg ('%s: downloading' % (feed))
    from twisted.web import client
    return client.getPage (feed.href, timeout = config.feed_fetch_timeout, agent = 'rssr')

def refresh_feeds ():
    session = db.Session ()

    from sqlalchemy import sql
    feeds = session.query (db.Feed).order_by (sql.func.random ())
    groups = [[] for f in xrange (config.deferred_groups)]
    for i, feed in enumerate (feeds):
        session.expunge (feed)
        groups[i % config.deferred_groups].append (feed)

    for g in groups:
        # This Deferred will call each callback as soon as it is added.
        # <http://twistedmatrix.com/documents/current/api/twisted.internet.defer.html#succeed>
        # The argument is passed to the first callback added.
        from twisted.internet import defer
        d = defer.succeed (None)
        for feed in g:
            # download_feed returns a deferred, which causes d's callback
            # chain to wait for the returned callback chain to be processed.
            # <http://twistedmatrix.com/projects/core/documentation/howto/defer.html#auto11>.
            d.addCallback (download_feed, feed)
            #d.addErrback (handle_403) # but if we handle a 403, what do we return? whatever we do will go to parse_feed

            d.addCallback (parse_feed, feed)

            d.addCallback (save_feed, feed)

            # Finally, this errback traps any failures from this feed
            # so that the deferred can continue to process the next
            # feed.
            d.addErrback (handle_error, feed)

        d.addCallback (done)

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
