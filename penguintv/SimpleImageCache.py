# Written by Owen Williams
# see LICENSE for license information
import logging

import pycurl

class SimpleImageCache:
	"""Dead simple.  we keep all of the images _in_ram_ with a dictionary. OH YEAH"""
	
	def __init__(self):
		self.image_dict={}
		
	def is_cached(self, url):
		if self.image_dict.has_key(url):
			return True
		return False
		
	def _check_cache(self, url):
		if len(self.image_dict) > 100:  #flush it every so often
			del self.image_dict
			self.image_dict = {}
		if self.image_dict.has_key(url):
			return self.image_dict[url]
		return None
		
	def get_image_from_file(self, filename):
		url = "file://" + filename
		cache = self._check_cache(url)
		if cache is not None:
			return cache
			
		try:
			f = open(filename, "rb")
			self.image_dict[url]=f.read()
			f.close()
		except Exception, e:
			logging.error("Error retrieving local file: %s" % (str(e),))
			self.image_dict[url] = ""
			
		return self.image_dict[url]
		
	def get_image(self, url):
		cache = self._check_cache(url)
		if cache is not None:
			return cache
			
		if url[0:4] == "file":
			filename = url.split("file://")[1]
			return self.get_image_from_file(filename)
		else:
			return self._get_http_image(url)
			
	def _get_http_image(self, url):
		d = SimpleImageCache.downloader()
		c = pycurl.Curl()
		c.setopt(pycurl.URL, url)
		c.setopt(pycurl.WRITEFUNCTION, d.body_callback)
		c.setopt(pycurl.CONNECTTIMEOUT, 7) #aggressive timeouts
		c.setopt(pycurl.TIMEOUT, 20) #aggressive timeouts
		c.setopt(pycurl.FOLLOWLOCATION, 1)
		try:
			c.perform()
			c.close()
		except:
			self.image_dict[url]=""
		self.image_dict[url]=d.contents
		return d.contents
			
	class downloader:
		def __init__(self):
			self.contents = ''

		def body_callback(self, buf):
			self.contents = self.contents + buf
