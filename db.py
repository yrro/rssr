from datetime import datetime

import config

from sqlalchemy import create_engine
engine = create_engine (config.db_engine)

from sqlalchemy.orm import sessionmaker
Session = sessionmaker (bind = engine, transactional = True, autoflush = True)

from sqlalchemy import MetaData
metadata = MetaData ()

from sqlalchemy import Table, Column, ForeignKey, func
from sqlalchemy import Integer, String, Unicode, DateTime, Boolean

feeds_table = Table ('feeds', metadata,
    Column ('id', Integer, primary_key = True),
    Column ('href', String, unique = True, nullable = False),
    Column ('version', Unicode),
    Column ('title', Unicode),
    Column ('link', Unicode),
    Column ('error', Unicode),
    Column ('refreshed', DateTime),
    Column ('updated', DateTime),
    schema = 'rssr')

entries_table = Table ('entries', metadata,
    Column ('id', Unicode, primary_key = True),
    Column ('feed_id', Integer, ForeignKey ('rssr.feeds.id'), primary_key = True),
    Column ('title', Unicode),
    Column ('link', Unicode),
    Column ('content', Unicode),
    Column ('summary', Unicode),
    Column ('published', DateTime),
    Column ('updated', DateTime),
    Column ('created', DateTime),
    Column ('author', Unicode),
    Column ('read', Boolean, nullable = False), # TODO: replace with a datetime?
    Column ('inserted', DateTime, nullable = False),
    # TODO: tags
    schema = 'rssr')

# tags

from sqlalchemy import sql

class Feed (object):
    def __init__ (self, href):
        self.href = href
    
    def __repr__ (self):
        return '<Feed %s "%s">' % (self.id, self.get_title ())
    
    def __unicode__ (self):
        return self.get_title ()

    def __str__ (self):
        return unicode (self).encode ('unicode_escape')

    def get_title (self):
        if self.title != None:
            return self.title
        return self.href
    
    def update_fields (self, parsed):
        self.version = parsed['version']
        if self.version == '':
            self.version = None

        if parsed.get ('bozo', 0) != 0:
            self.error = str (parsed.bozo_exception)
        else:
            self.error = None

        self.title = parsed['feed'].get ('title')
        self.link = parsed['feed'].get ('link')
        self.http_modified = parsed.get ('modified')
        self.http_etag = parsed.get ('etag')
        self.refreshed = datetime.utcnow ()

        if parsed['feed'].has_key ('updated_parsed'):
            self.updated = datetime (*parsed['feed']['updated_parsed'][0:6])
        else:
            self.updated = None

class Entry (object):
    def update_fields (self, parsed_entry):
        if self.id != None:
            assert self.id == parsed_entry['id'], 'Tried to set new id "%s" for "%s"' % (parsed_entry['id'], self)
        else:
            self.id = parsed_entry['id']

        self.title = parsed_entry.get ('title')
        self.link = parsed_entry.get ('link')
        self.summary = parsed_entry.get ('summary')
        self.published = parsed_entry.get ('published')
        self.updated = parsed_entry.get ('updated')
        self.created = parsed_entry.get ('created')
        self.author = parsed_entry.get ('author')
        
        if len (parsed_entry.get ('content', [])) > 0:
            self.content = parsed_entry['content'][0].value

    def  __repr__ (self):
        return '<Entry %s (%s)>' % (self.id, self.feed.id)

    def __unicode__ (self):
        return u'%s (%s)' % (self.get_title (), self.feed.get_title ())

    def __str__ (self):
        return unicode (self).encode ('unicode_escape')

    def get_title (self):
        if self.title != None:
            return self.title
        return self.id

from sqlalchemy.orm import mapper, relation
mapper (Feed, feeds_table, properties = {'entries': relation (Entry, backref = 'feed', lazy = 'dynamic')})
mapper (Entry, entries_table)

if __name__ == '__main__':
    metadata.create_all (bind = engine)
