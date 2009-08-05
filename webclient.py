from twisted.internet import reactor
from twisted.web import client

# http://twistedmatrix.com/pipermail/twisted-web/2004-November/000835.html
def getPage (url, contextFactory = None, *args, **kwargs):
    '''Download a web page as a string.

    Download a page. Return a HTTPClientFactory containing a 'deferred'
    attribute, which will callback with a page (as a string) or errback with a
    description of the error.
    
    Based on the twisted.web.client.getPage function.'''
    scheme, host, port, path = client._parse (url)
    factory = client.HTTPClientFactory (url, *args, **kwargs)
    if scheme == 'https':
        from twisted.internet import ssl
        if contextFactory is None:
            contextFactory = ssl.ClientContextFactory ()
        reactor.connectSSL (host, port, factory, contextFactory)
    else:
        reactor.connectTCP (host, port, factory)
    return factory

# vim: noet sts=4
