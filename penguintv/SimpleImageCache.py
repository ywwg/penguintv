# Written by Owen Williams
# see LICENSE for license information
import logging
import threading

import pycurl

__MAX_IMAGES__ = 250

class SimpleImageCache:
	"""Dead simple.  we keep all of the images _in_ram_ with a dictionary. OH YEAH"""
	
	def __init__(self):
		self.image_dict={}
		self.image_list=[]
		self._update_lock = threading.Lock()
		
	def is_cached(self, url):
		self._update_lock.acquire()
		if self.image_dict.has_key(url):
			self._update_lock.release()
			return True
		self._update_lock.release()
		return False
		
	def _check_cache(self, url):
		self._update_lock.acquire()
		if len(self.image_dict) > __MAX_IMAGES__:  #flush it every so often
			url_to_delete = self.image_list.pop(0)
			self.image_dict.pop(url_to_delete)
		if self.image_dict.has_key(url):
			image = self.image_dict[url]
			self._update_lock.release() 
			return image
		self._update_lock.release()
		return None
		
	def get_image_from_file(self, filename):
		url = "file://" + filename
		cache = self._check_cache(url)
		if cache is not None:
			#logging.debug("cached")
			return cache

		self._update_lock.acquire()
		try:
			f = open(filename, "rb")
			image = self.image_dict[url] = f.read()
			self.image_list.append(url)
			f.close()
		except Exception, e:
			logging.error("Error retrieving local file: %s" % (str(e),))
			image = self.image_dict[url] = ""
			self.image_list.append(url)

		self._update_lock.release()			
		return image
		
	def get_image(self, url):
		cache = self._check_cache(url)
		if cache is not None:
			return cache
			
		if url[0:4] == "file":
			#logging.debug("local")
			filename = url[7:]
			return self.get_image_from_file(filename)
		else:
			#logging.debug("remote")
			return self._get_http_image(url)
			
	def _get_http_image(self, url):
		d = SimpleImageCache.Downloader(url)
		d.download()
		self._update_lock.acquire()
		image = self.image_dict[url] = d.contents
		self.image_list.append(url)
		self._update_lock.release()
		return image
			
	class Downloader:
		def __init__(self, url):
			self._url = url
			self.contents = ''
		
		def download(self):
			c = pycurl.Curl()
			try:
				c.setopt(pycurl.URL, str(self._url).strip())
			except Exception, e:
				logging.error("Error downloading file: %s %s" % (self._url,str(e)))
				return ""
		
			c.setopt(pycurl.WRITEFUNCTION, self.body_callback)
			c.setopt(pycurl.CONNECTTIMEOUT, 7) #aggressive timeouts
			c.setopt(pycurl.TIMEOUT, 20) #aggressive timeouts
			c.setopt(pycurl.FOLLOWLOCATION, 1)
			c.setopt(pycurl.NOSIGNAL, 1) #multithread ok
			try:
				c.perform()
				c.close()
			except:
				self.contents = ""
		
		def body_callback(self, buf):
			self.contents = self.contents + buf
