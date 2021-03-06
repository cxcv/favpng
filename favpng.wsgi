#!/usr/bin/env pypy
# -*- coding: utf-8 -*-
# vim: ts=4 syntax=python
#
# Copyright (c) 2009-2014 Benjamin Schweizer.
#

import sys; sys.path.insert(0, '/srv/www/vhosts/magnumchaos.org/lib/site-packages')
import time
DEBUG=False
try:
    # https://github.com/cxcv/python-tracebackturbo
    import tracebackturbo as traceback
except ImportError:
    import traceback
CACHE=None
try:
    if not DEBUG:
        import memcache; CACHE = memcache.Client(['127.0.0.1:11211'])
except ImportError:
    pass

ENVIRON={}
def log(str):
    ENVIRON['wsgi.errors'].write('%s\n' % str)

chars_alnum='abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890'
chars_hostname=chars_alnum+'.-_'
chars_0to31 = ''.join(map(chr, range(0,32))) # ascii control characters
chars_32to127 = ''.join(map(chr, range(32,128)))
chars_mozbad = chars_0to31 + u''.join(map(unichr, [
    0x0020, 0x00a0, 0x00bc, 0x00bd, 0x00be, 0x01c3, 0x02d0, 0x0337, 0x0338,
    0x0589, 0x05c3, 0x05f4, 0x0609, 0x060a, 0x066a, 0x06d4, 0x0701, 0x0702,
    0x0703, 0x0704, 0x115f, 0x1160, 0x1735, 0x2000, 0x2001, 0x2002, 0x2003,
    0x2004, 0x2005, 0x2006, 0x2007, 0x2008, 0x2009, 0x200a, 0x200b, 0x2024,
    0x2027, 0x2028, 0x2029, 0x202f, 0x2039, 0x203a, 0x2041, 0x2044, 0x2052,
    0x205f, 0x2153, 0x2154, 0x2155, 0x2156, 0x2157, 0x2158, 0x2159, 0x215a,
    0x215b, 0x215c, 0x215d, 0x215e, 0x215f, 0x2215, 0x2236, 0x23ae, 0x2571,
    0x29f6, 0x29f8, 0x2afb, 0x2afd, 0x2ff0, 0x2ff1, 0x2ff2, 0x2ff3, 0x2ff4,
    0x2ff5, 0x2ff6, 0x2ff7, 0x2ff8, 0x2ff9, 0x2ffa, 0x2ffb, 0x3000, 0x3002,
    0x3014, 0x3015, 0x3033, 0x3164, 0x321d, 0x321e, 0x33ae, 0x33af, 0x33c6,
    0x33df, 0xa789, 0xfe14, 0xfe15, 0xfe3f, 0xfe5d, 0xfe5e, 0xfeff, 0xff0e,
    0xff0f, 0xff61, 0xffa0, 0xfff9, 0xfffa, 0xfffb, 0xfffc, 0xfffd
]))

def chars_in_list(str, valid_chars):
    """returns true if all chars of str are contained in valid_chars"""
    for c in str:
        if not c in valid_chars:
            return False
    return True


import urllib, urlparse
def urinorm2(uri, referrer=None, encoding='utf-8'):
    """normalize uris"""
    __ports = { 
        "http": 80, 
        "https": 443,
        "ftp": 21, 
    }
    # split fields
    scheme, authority, path, query, fragment = httplib2.parse_uri(uri)
    if not scheme or not authority:
        if not referrer:
            raise Exception('uri is relative and no referrer was given')
        referrer = urinorm2(referrer)
        uri = urlparse.urljoin(referrer, uri)
        scheme, authority, path, query, fragment = httplib2.parse_uri(uri)

    # normalize fields
    scheme = scheme.lower()
    authority = authority.lower()
    host = authority
    if not scheme in __ports.keys():
        raise Exception('unsupported scheme found: %s' % scheme)
    port = __ports[scheme]
    if ':' in authority:
        host, port = authority.split(':')
        port = int(port)
    if not path:
        path = '/'

    # encodings
    if isinstance(scheme, unicode):
        scheme = scheme.encode('ascii')
    if isinstance(host, unicode):
        host = host.encode('idna')
    if not chars_in_list(host, chars_hostname):
        raise Exception('hostname is binary encoded and contains invalid characters')
    if isinstance(path, unicode):
        path = path.encode('utf-8')
    path = urllib.quote(path, safe=chars_32to127)
    if isinstance(query, unicode):
        query = query.encode('utf-8')
    if query:
        query = urllib.quote(query, safe=chars_32to127)
    if isinstance(fragment, unicode):
        fragment = fragment.encode('utf-8')
    if fragment:
        fragment = urllib.quote(fragment, safe=chars_32to127)

    # re-build uri
    uri = scheme + '://' + host
    if not port == __ports[scheme]:
        uri += ':' + str(port)
    uri += path
    if query:
        uri += '?' + query
    if fragment:
        uri += '#' + fragment

    assert(isinstance(uri, str))
    return uri

import HTMLParser
def links(html, rels, types=False, referrer=None):
    """get links from html page header"""
    class LinkParser(HTMLParser.HTMLParser):
        dompath = []
        result = []
        def __init__(self, rels, types, referrer):
            HTMLParser.HTMLParser.__init__(self)
            self.rels = rels
            self.types = types
            self.referrer = referrer

        def handle_starttag(self, tag, attrs):
            tag = tag.lower()

            # html: tags that don't need closing
            if not tag in ['meta', 'link', 'br']:
                self.dompath.append(tag)

            # firefox behaviour: accept links outside header
            #if self.dompath == ['html', 'head'] and tag == 'link':
            if tag == 'link':
                self.handle_link(attrs)

        def handle_endtag(self, tag):
            tag = tag.lower()
            if not self.dompath:
                return

            stag = self.dompath.pop()

            if stag != tag:
                # ignore wrong closing tag
                self.dompath.append(stag)
                return

        def handle_link(self, attrs):
            link_title = False
            link_type = False
            link_href = False
            link_rel = False

            for (k,v) in attrs:
                k = k.lower()
                if k == 'rel': link_rel = v.lower()
                if k == 'type': link_type = v.lower()
                try:
                    if k == 'href': link_href = urinorm2(v, self.referrer)
                except: # skip attribute
                    continue
                if k == 'title': link_title = v

            if link_href and link_rel in self.rels and (not self.types or link_type in self.types):
                self.result.append(link_href)

    assert(isinstance(html, unicode))
    parser = LinkParser(rels, types, referrer)
    for word in html.split('>'):
        try:
            parser.feed(word+'>')
        except HTMLParser.HTMLParseError:
            parser.reset()
    return parser.result


import magickwand
def convert(wand, width, height, depth):
    """extrace or convert image to given dimensions"""
    magickwand.MagickResetIterator(wand)
    # i) find exact match
    has_image= True
    while has_image:
        _width = magickwand.MagickGetImageWidth(wand)
        _height = magickwand.MagickGetImageHeight(wand)
        _depth = magickwand.MagickGetImageChannelDepth(wand, magickwand.AlphaChannel)
        if _width == width and _height == height and _depth == depth:
            return
        has_image = magickwand.MagickNextImage(wand)

    # ii) find any match
    magickwand.MagickResetIterator(wand)
    has_image= True
    while has_image:
        _width = magickwand.MagickGetImageWidth(wand)
        _height = magickwand.MagickGetImageHeight(wand)
        if _width == width and _height == height:
            return
        has_image = magickwand.MagickNextImage(wand)

    # iii) fall back to scaling
    if not magickwand.MagickScaleImage(wand, width, height):
        raise magickwand.WandException(wand)
    return

def img2png(buf, ctype):
    """i/o wrapper for convert"""
    try:
        magick_wand = magickwand.NewMagickWand()
        magickwand.MagickSetFilename(magick_wand, 'buffer.%s' % ctype) # hint
        if not magickwand.MagickReadImageBlob(magick_wand, buf, len(buf)):
            raise magickwand.WandException(wand)
        
        convert(magick_wand, 16, 16, 8)

        magickwand.MagickSetFilename(magick_wand, 'buffer.png') # hint
        #size = magickwand.size_t()
        size = magickwand.magickwand5.c_ulong()
        buf = magickwand.MagickGetImageBlob(magick_wand, size)
        result = ''.join([chr(buf[i]) for i in range(0, size.value + 1)])
        magickwand.MagickRelinquishMemory(buf)
    finally:
        magickwand.DestroyMagickWand(magick_wand)
    return result

import httplib2, socket
import codecs
def dotherightthing(uri):
    if DEBUG: log('uri = %s' % uri)
    if uri.startswith('uri='):
        #uri = uri[4:]
        uri = urllib.unquote(uri[4:]) #.decode('utf8')
    if DEBUG: log('uri4 = %s' % uri)

    if uri == '':
        return {'location': 'about.html', 'x-debug': 'no args'}, '', '302 Go Ahead!'

    try:
        uri = urinorm2(uri)
        if not uri.split('://')[0] in ['http', 'https']:
            raise Exception('schema not supported')
    except Exception, err:
        # broken uris
        if DEBUG: log('broken uri %s: %s' % (uri, err))
        return {'location': 'icons/500.png', 'x-debug': 'network'}, '', '302 Go Ahead!'

    if CACHE:
        key = ('favpng_%s' % uri)[:250]
        result = CACHE.get(key)
        if result:
            return result

    headers = {
        'User-Agent': 'favpng (+%s)' % ENVIRON['SCRIPT_URI'],
        'Cache-Control': 'max-age=%s, public' % (24*3600), # seconds
        'Connection': 'close', # reusing sockets consumes too many fds as we are not thread-safe
        'Accept-Encoding': 'compress,gzip', # bug with deflate junk header, see zdf.de; reported httplib2-0.5 upstream
    }
    try:
        http = httplib2.Http(timeout=10, disable_ssl_certificate_validation=True)
        response, content = http.request(uri , 'GET', headers=headers)
    except (socket.error, socket.timeout, httplib2.ServerNotFoundError, httplib2.FailedToDecompressContent, httplib2.httplib.ResponseNotReady, httplib2.RedirectLimit) as err:
        if DEBUG: log('error %s' % err)
        return {'location': 'icons/500.png', 'x-debug': 'network'}, '', '302 Go Ahead!'
    except:
        log('%s' % traceback.format_exc())
        return {'location': 'icons/500.png', 'x-debug': 'network-exception'}, '', '302 Go Ahead!'

    # pass redirects
    if 'content-location' in response and urinorm2(response['content-location'], uri) != uri or \
        response.status in [301, 302, 303, 304, 307]:
        redirect_uri = '%s?%s' % (ENVIRON['SCRIPT_URI'], urinorm2(response['content-location'], uri))
        return {'location': redirect_uri, 'x-debug': 'passed redirect'}, '', '302 Go Ahead!'

    # empty body
    if not len(content) or response.status != 200:
        redirect_uri = '%s?%s' % (ENVIRON['SCRIPT_URI'], urinorm2('/', uri))
        return {'location': redirect_uri, 'x-debug': 'nothing found'}, '', '302 Go Ahead!'
        
    # split&process content-type field: Content-Type: application/xml; charset=ISO-8859-1; filename=feed.xml
    if DEBUG: log('original content-type = %s' % response.get('content-type', None))    # default
    content_type = response.get('content-type', 'application/octet-stream').lower()     # default
    content_encoding = 'ascii'
    for _value in content_type.split(';'):
        if '=' in _value:
            _key, _value = _value.split('=')
        else:
            _key = 'content-type'
        _key = _key.strip()
        _value = _value.strip()

        if _key == 'content-type':
            content_type = _value
            mime_overwrites = [
                (('.htm', '.html'),     'text/html'),
                (('.ico'),              'image/ico'),
                (('.png'),              'image/png'),
                (('.gif'),              'image/gif'),
                (('.jpg', '.jpeg'),     'image/jpeg'),
                (('rss', 'rss/'),       'application/rss+xml'),
                (('atom', 'atom/'),     'application/rss+xml'),
            ]
            # prefer file ending for some types
            if _value in ['application/octet-stream', 'application/xml', 'text/xml']:
                for ending, mimetype in mime_overwrites:
                    if uri.lower().endswith(ending):
                        _value = mimetype

        if _key == 'charset': # find content-encoding
            content_encoding = _value
            if content_encoding == 'utf-8lias': content_encoding = 'utf-8' # dilbert.com
            try:
                codecs.lookup(content_encoding)
            except LookupError:
                log('found unknown encoding %s at %s' % (content_encoding, uri))
                content_encoding = 'ascii'

    # overwrite content-type for very special filename 'favicon.ico'
    if uri.endswith('favicon.ico'):
        content_type = 'image/ico'

    if DEBUG: log('final content-type = %s, content-encoding = %s' % (content_type, content_encoding))

 
    # images
    if content_type in ['image/png', 'image/gif', 'image/ico', 'image/x-icon', 'image/vnd.microsoft.icon', 'image/jpeg', 'application/octet-stream']:
        extension = {
            'image/png': 'png',
            'image/gif': 'gif',
            'image/ico': 'ico',
            'image/x-icon': 'ico',
            'image/vnd.microsoft.icon': 'ico',
            'application/octet-stream': 'ico', # hp.com
            'image/jpeg': 'jpeg', # http://unix.rulez.org/
        }[content_type]
        try:
            body = img2png(content, extension)
            return {'content-type': 'image/png'}, body, '200 Thank You!'
        except Exception ,e:
            # fixme: log error
            log('img2png failed for %s at %s' % (content_type, uri))
            if DEBUG: raise #log('  exception: %s' % e)
            # continue


    # html
    if content_type in ['text/html', 'text/plain', 'application/xml', 'text/xml', 'application/octet-stream', 'application/xhtml+xml']:
        if DEBUG: log('parsing as html')
        content_decoded = content.decode(content_encoding, 'ignore')

        l = links(content_decoded, rels=['icon', 'shortcut icon'], referrer=uri)

        if DEBUG: log('found links: %s' % l)

        if l:
            redirect_uri = '%s?%s' % (ENVIRON['SCRIPT_URI'], l[0])
            return {'location': redirect_uri, 'x-debug': 'html'}, '', '302 Go Ahead!'
        # else: continue


    # feeds
    if content_type in ['application/rss+xml', 'application/atom+xml', 'application/rdf+xml', 'application/xml', 'text/xml', 'application/octet-stream']:
        try:
            import feedparser
            if DEBUG: log('parsing as feed')
            f = feedparser.parse(content)
            for link in f.feed.get('links', []):
                if link.type in ['text/html']:
                    if DEBUG: log('found link %s' % link.href)
                    redirect_uri = '%s?%s' % (ENVIRON['SCRIPT_URI'], urinorm2(link.href, referrer=uri))
                    return {'location': redirect_uri, 'x-debug': 'feed'}, '', '302 Go Ahead!'
            if DEBUG: log('no link found at %s' % uri)

            if "image" in f.feed:
                redirect_uri = '%s?%s' % (ENVIRON['SCRIPT_URI'], urinorm2(f.feed.image.href, referrer=uri))
                return {'location': redirect_uri, 'x-debug': 'feed'}, '', '302 Go Ahead!'
            if DEBUG: log('no image found at %s' % uri)
            if DEBUG: log('dump: %s' % f.feed)
        except ImportError, AttributeError:
            log('feedparser failed for %s at %s' % (content_type, uri))
        # try to load frontpage
        redirect_uri = '%s?%s' % (ENVIRON['SCRIPT_URI'], urinorm2('/', uri))
        return {'location': redirect_uri, 'x-debug': 'frontpage'}, '', '302 Go Ahead!'

    if DEBUG: log('continue')
    # fixed icons
    fixedicons = {
        'application/pdf': 'icons/pdf.png',
    }
    if content_type in fixedicons:
        return {'location': fixedicons[content_type], 'x-debug': 'fixed'}, '', '302 Go Ahead!'

    # unmatched content-types
    if not content_type in [
            'text/html', 'text/plain', 'application/xml', 'application/xhtml+xml',
            'application/rss+xml', 'application/atom+xml', 'text/xml', 'application/rdf+xml', 'application/xml',
            'image/png', 'image/gif', 'image/ico', 'image/x-icon', 'image/vnd.microsoft.icon', 'application/octet-stream', 'image/jpeg'
        ]:
        log('unmatched content type %s at %s' % (content_type, uri))
    redirect_uri = '%s?%s' % (ENVIRON['SCRIPT_URI'], urinorm2('/favicon.ico', referrer=uri))
    return {'location': redirect_uri, 'x-debug': 'content-type'}, '', '302 Go Ahead!'

def application(environ, start_response):
    global ENVIRON; ENVIRON=environ
    try:
        uri = environ['QUERY_STRING']
        headers, body, status = dotherightthing(uri)
        if CACHE:
            key = ('favpng_%s' % uri)[:250]
            CACHE.set(key, (headers, body, status), time=30*24*3600)
    except:
        log('%s' % traceback.format_exc())
        headers, body, status = {'location': 'icons/500.png', 'x-debug': 'fatal exception'}, '', '302 Go Ahead!'

    # redirection loop
    #redirect_uri = '%s?%s' % (ENVIRON['SCRIPT_URI'], urinorm2('/favicon.ico', referrer=uri))
    if headers.get('location', '').endswith(environ['QUERY_STRING']) and environ['QUERY_STRING'] != '':
        redirect_uri = '%s?%s' % (ENVIRON['SCRIPT_URI'], urinorm2('/favicon.ico', referrer=uri))
        headers, body, status = {'location': redirect_uri, 'x-debug': 'redirection loop'}, '', '302 Go Ahead!'

    # redirection after final destination
    if headers.get('location', None) and environ['QUERY_STRING'].endswith('/favicon.ico'):
        headers, body, status = {'location': 'icons/404.png', 'x-debug': 'final loop'}, '', '302 Go Ahead!'

    if isinstance(body, unicode):
        body=body.encode("utf-8")

    if not 'expires' in headers:
        expires = time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime(time.time()+7*24*3600))
        headers['expires'] = expires
    headers['content-length'] = str(len(body))

    start_response(status, headers.items())
    return [body]

if __name__ == '__main__':
    #uri = u"http://WWW.xn--mller-kva.de_www.müller.DE_www.m%C3%BCller.de/%61%62%63_foo__baräöü%C3%A4%C3%B6%C3%BC?baz"
    # scheme, authority, path, query, fragment = 'https', 'www.example.com:8443', '/foo.php?bar=baz', 'https://www.example.com:8443/foo.php?bar=baz'
    #for u in ['http://www.xn--mller-kva.de/xn--mller-kva', u'http://www.müller.de/müller', 'http://www.m%C3%BCller.de/m%C3%BCller', 'http://www.example.com:80/foo?', 'https://www.example.com:8443/foo.php?bar=baz#bau', '/relative']:
    #for u in ['http://www.example.com:80/foo?', 'https://www.example.com:8443/foo.php?bar=baz#bau', '/relative', 'http://www.example.com', '/über', u'HTTP://WWW.MÜLLER.DE:80']:
    #    print u
    #    print urinorm2(u, "http://www.google.de:80")
    #    print '---'
    #raise SystemExit()

    DEBUG=True
    CACHE=None
    import sys
    def sr(status, response_headers):
        print response_headers
        print status

    uri = sys.argv[1]
    print application(environ={'SCRIPT_URI': 'http://www.example.com/favpng.wsgi', 'QUERY_STRING': '%s' % uri, 'wsgi.errors': sys.stderr}, start_response=sr)[0]

# eof.
