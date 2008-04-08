# itunes.py
# Written by Owen Williams, (c) 2007
# see LICENSE for license information
#
# iTunes has very strange weblinks, but they are not that hard to read.
# A "viewPodcast" link returns a gzipped web page that contains a link that
# iTunes can load.  Although the protocol of this link is itms://, we can
# load it with http.  This time we get a gzipped xml file, and toward the
# bottom of the file is a simple key / value pair for episodeURL.  This
# url is what the podcast author has told itunes to use, and it'll be regular
# RSS (we hope).


import sys
import gzip
import urllib
import HTMLParser

from xml.sax import saxutils, make_parser
from xml.sax.handler import feature_namespaces

def is_itunes_url(url):
	""" Two simple checks to see if this is a valid itunes url:
		(ie, http://phobos.apple.com/WebObjects/MZStore.woa/wa/viewPodcast?id=207870198)
	    * does it contain "phobos.apple.com", and
	    * does it contain "viewPodcast" 
	    
	    There's also another form, as in http://www.itunes.com/podcast?id=207870198"""
	    
	if "phobos.apple.com/" in url.lower() and "viewPodcast" in url:
		return True
	if "itunes.com/podcast" in url.lower():
		return True
	return False

def get_rss_from_itunes(url):
	if not is_itunes_url(url):
		raise ItunesError, "not an itunes url"

	# Part 1, get the itunes "webpage" for this feed
	# we have to save the file because urlopen doesn't support seeking		
	filename, message = urllib.urlretrieve(url)
	uncompressed = gzip.GzipFile(filename=filename, mode='r')

	parser = viewPodcastParser()
	parser.feed(uncompressed.read())

	if parser.url is None:
		raise ItunesError, "error getting viewpodcast url from itunes"
		
	# Part 2, find the actual rss link in the itunes "webpage"
	filename, message = urllib.urlretrieve(parser.url)
	uncompressed = gzip.GzipFile(filename=filename, mode='r')

	parser = make_parser()
	parser.setFeature(feature_namespaces, 0)
	handler = itunesHandler()
	parser.setContentHandler(handler)
	parser.parse(uncompressed)

	if handler.url is None:
		raise ItunesError, "error finding podcast url"
		
	return handler.url

class viewPodcastParser(HTMLParser.HTMLParser):
	def __init__(self):
		HTMLParser.HTMLParser.__init__(self)
		self.url = None
		
	def handle_starttag(self, tag, attrs):
		new_attrs = []
		if tag.upper() == "BODY":
			for attr, val in attrs:
				if attr == "onload":
					url = val[val.find("itms://") + 4:]
					url = url[:url.find("'")]
					url = "http" + url
					self.url = url
					
class itunesHandler(saxutils.DefaultHandler):
	def __init__(self):
		self.url = ""
		self._in_key = None
		self._in_value = None
		self._last_key = None

	def startElement(self, name, attrs):
		if name == 'key':
			self._in_key = ""
		elif name == 'string':
			self._in_value = ""

	def endElement(self, name):
		if name == 'key':
			self._last_key = self._in_key
			self._in_key = None
		elif name == 'string':
			if self._last_key == 'feedURL':
				self.url = self._in_value
			self._in_value = None
				
	def characters(self, ch):
		if self._in_key is not None:
			self._in_key += ch
		elif self._in_value is not None:
			self._in_value += ch
			
class ItunesError(Exception):
	def __init__(self, m):
		self.m = m
	def __str__(self):
		return m



