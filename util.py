import cgi
import datetime
import htmlentitydefs
import re
import sha
import subprocess

_char_ent_ref = re.compile ('&([A-Za-z0-9]+);')
_h_num_char_ref = re.compile ('&#x([0-9A-Fa-f]+);')
_d_num_char_ref = re.compile ('&#([0-9]+);')

def _char_ent_ref_sub (match):
    r = match.group (1)
    try:
        return '&#%s;' % (htmlentitydefs.name2codepoint[r])
    except KeyError:
        return '&%s;' % (r)

def decode_entities (data, html = False):
    if html:
        data = _char_ent_ref.sub (_char_ent_ref_sub, data)
    data = _h_num_char_ref.sub (lambda match: unichr (int (match.group (1), 16)), data)
    data = _d_num_char_ref.sub (lambda match: unichr (int (match.group (1))), data)

    return data

def render_html_to_plaintext (html):
    '''Turn some HTML into plain text. Returns a unicode object.'''
    p = subprocess.Popen (['w3m', '-dump', '-T', 'text/html'],
        stdin = subprocess.PIPE,
        stdout = subprocess.PIPE)
    output = p.communicate (html.encode ('utf-8'))[0]
    if p.returncode != 0:
        raise Exception ('w3m failed (status %i)' % (p.returncode))
    return output.decode ('utf-8')

def struct_time_to_datetime (time):
    if time == None:
        return None

    return datetime.datetime (*time[0:6])

def feedparser_entry_guid (entry_parsed):
    '''Some feeds lack a sensible guid. We'll just have to use other
    elements of the feed instead.'''
    if entry_parsed.get ('id') != None:
        return entry_parsed['id']

    return unicode (sha.new (repr (dict (entry_parsed))).hexdigest ())

# vim: softtabstop=4 expandtab
