from datetime import datetime

import config
import util

from sqlalchemy import create_engine
engine = create_engine (config.db_engine)

from sqlalchemy.orm import sessionmaker
Session = sessionmaker (bind = engine, transactional = True, autoflush = True)

from sqlalchemy import MetaData
metadata = MetaData ()

from sqlalchemy import Table, Column, ForeignKey, CheckConstraint
from sqlalchemy import Integer, String, Unicode, DateTime, Boolean

feeds_table = Table ('feeds', metadata,
    Column ('id', Integer, primary_key = True),
    Column ('href', String, unique = True, nullable = False),
    Column ('version', Unicode),
    Column ('title_value', Unicode),
    Column ('title_type', String),
    CheckConstraint ('title_value IS NULL = title_type IS NULL', name = 'title_has_type'),
    CheckConstraint ("title_value != ''", name = 'title_not_empty'),
    Column ('link', Unicode),
    Column ('error', Unicode),
    Column ('refreshed', DateTime),
    Column ('updated', DateTime),
    schema = 'rssr')

entries_table = Table ('entries', metadata,
    Column ('id', Unicode, primary_key = True),
    Column ('feed_id', Integer, ForeignKey ('rssr.feeds.id'), primary_key = True),
    Column ('title_value', Unicode),
    Column ('title_type', String),
    CheckConstraint ('title_value IS NULL = title_type IS NULL', name = 'title_has_type'),
    CheckConstraint ("title_value != ''", name = 'title_not_empty'),
    Column ('link', Unicode),
    Column ('content_value', Unicode),
    Column ('content_type', String),
    CheckConstraint ('content_value IS NULL = content_type IS NULL', name = 'content_has_type'),
    CheckConstraint ("content_value != ''", name = 'content_not_empty'),
    Column ('summary_value', Unicode),
    Column ('summary_type', String),
    CheckConstraint ('summary_value IS NULL = summary_type IS NULL', name = 'summary_has_type'),
    CheckConstraint ("summary_value != ''", name = 'summary_not_empty'),
    Column ('published', DateTime),
    Column ('updated', DateTime),
    Column ('created', DateTime),
    Column ('author', Unicode),
    Column ('read', Boolean, nullable = False), # TODO: replace with a datetime?
    Column ('inserted', DateTime, nullable = False),
    schema = 'rssr')

# tags

from sqlalchemy import sql

class Feed (object):
    def __init__ (self, href):
        self.href = href
    
    def __repr__ (self):
        return '<Feed "%s">' % (self.get_title ().encode ('unicode_escape'))
    
    #def __unicode__ (self):
    #    return self.get_title ()

    #def __str__ (self):
    #    return unicode (self).encode ('unicode_escape')

    def get_title (self):
        t = self.title.as_text ()
        if t != None:
            return t
        return self.href
    
    def update_fields (self, parsed):
        self.version = parsed['version']
        if self.version == '':
            self.version = None

        if parsed.get ('bozo', 0) != 0:
            self.error = str (parsed.bozo_exception)
        else:
            self.error = None

        if parsed['feed'].get ('title_detail'):
            self.title = MaybeHTML (parsed['feed']['title_detail']['value'], parsed['feed']['title_detail']['type'])
        else:
            self.title = MaybeHTML.None_

        self.link = parsed['feed'].get ('link')
        self.refreshed = datetime.utcnow ()
        self.updated = util.struct_time_to_datetime (parsed['feed'].get ('updated_parsed'))

class Entry (object):
    def update_fields (self, parsed_entry):
        if self.id != None:
            if self.id != parsed_entry['id']:
                raise Exception ('Tried to set new id "%s" for %s' % (parsed_entry['id'].encode ('unicode_escape'), repr (self)))
        else:
            self.id = parsed_entry['id']

        if parsed_entry.get ('title_detail'):
            self.title = MaybeHTML (parsed_entry['title_detail']['value'], parsed_entry['title_detail']['type'])
        else:
            self.title = MaybeHTML.None_

        if parsed_entry.get ('summary_detail'):
            self.summary = MaybeHTML (parsed_entry['summary_detail']['value'], parsed_entry['summary_detail']['type'])
        else:
            self.summary = MaybeHTML.None_
        
        self.published = util.struct_time_to_datetime (parsed_entry.get ('published_parsed'))
        self.updated = util.struct_time_to_datetime (parsed_entry.get ('updated_parsed'))
        self.created = util.struct_time_to_datetime (parsed_entry.get ('created_parsed'))

        self.link = parsed_entry.get ('link')
        self.author = parsed_entry.get ('author')
        
        if len (parsed_entry.get ('content', [])) > 0 and parsed_entry['content'][0]['value'] != u'':
            self.content = MaybeHTML (parsed_entry['content'][0]['value'], parsed_entry['content'][0]['type'])
        else:
            self.content = MaybeHTML.None_

    def  __repr__ (self):
        return '<Entry %s>' % (self.id.encode ('unicode_escape'))

    #def __unicode__ (self):
    #    return u'%s (%s)' % (self.get_title (), self.feed.get_title ())

    #def __str__ (self):
    #    return unicode (self).encode ('unicode_escape')

    def get_title (self):
        t = self.title.as_text ()
        if t != None:
            return t
        return self.id

class MaybeHTML (object):
    def __init__ (self, data, content_type):
        if data == None != content_type == None:
            raise Exception ('data and content_type must both be None or not-None')

        self.__data = data
        self.__content_type = content_type
    
    def __composite_values__ (self):
        return (self.__data, self.__content_type)

    def __eq__ (self, other):
        if other == None:
            return False
        return self.__data == other.__data and self.__content_type == other.content_type

    def __ne__ (self, other):
        return not self == other

    def as_text (self):
        '''Returns the content as a unicode object.'''
        if self.__content_type == None:
            return None
        if self.__content_type == 'text/plain':
            return self.__data
        if self.__content_type == 'text/html':
            return util.render_html_to_plaintext (self.__data)
        if self.__content_type == 'application/xhtml+xml':
            return util.decode_entities (self.__data)
        
        raise Exception ('Unknown content type "%s"' % (self.__content_type))
MaybeHTML.None_ = MaybeHTML (None, None)

from sqlalchemy.orm import mapper, relation, composite
mapper (Feed, feeds_table,
    properties = {
        'entries': relation (Entry, backref = 'feed', lazy = 'dynamic'),
        'title': composite (MaybeHTML, feeds_table.columns.title_value, feeds_table.columns.title_type)
    })
mapper (Entry, entries_table,
    properties = {
        'title': composite (MaybeHTML, entries_table.columns.title_value, entries_table.columns.title_type),
        'summary': composite (MaybeHTML, entries_table.c.summary_value, entries_table.c.summary_type),
        'content': composite (MaybeHTML, entries_table.c.content_value, entries_table.c.content_type)
    })

if __name__ == '__main__':
    metadata.create_all (bind = engine)

# vim: softtabstop=4 expandtab
