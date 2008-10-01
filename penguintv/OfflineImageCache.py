
### OfflineImageCache
#
# Implements local image caching for feeds, transparently to the rest of the 
# application.
#
# Has a threadpool.  Takes html and a GUID (entry_id) and downloads all the
# images to a storage location.  Hashes filenames based on url to prevent
# collisions.  
#
# Uses BeautifulSoup to rewrite html at render time to replace image tags with
# locally cached urls.
#
# Need better checking of disk space, etc

import urllib
import os.path
import pickle
import logging
import hashlib  #requires python2.5

import gobject

import utils
import ThreadPool
from BeautifulSoup.BeautifulSoup import BeautifulSoup


DEBUG = False

def threaded_callback():
	def annotate(func):
		def _exec_cb(self, *args, **kwargs):
			def timeout_func(self, func, *args, **kwargs):
				func(self, *args, **kwargs)
				return False
			if DEBUG:
				func(self, *args, **kwargs)
			else:
				gobject.idle_add(timeout_func, self, func, *args, **kwargs)
		return _exec_cb
	return annotate	

class OfflineImageCache:
	def __init__(self, store_location):
		#logging.debug("OFFLINE IMAGE CACHE STARTUP")
		self._store_location = store_location
		self._threadpool = ThreadPool.ThreadPool(5 ,"OfflineImageCache")
		self._cachers = {} # dict of urlcacher objects?
		
	def cache_html(self, guid, html):
		if self._cachers.has_key(guid):
			if self._cachers[guid]:
				#logging.debug("that cacher is already active, ignoring, %s" % str(guid))
				return
			
		self._cachers[guid] = True
		page_cacher = PageCacher(guid, html, self._store_location, self._threadpool, self._cache_cb)
		page_cacher.process()
		
	def _cache_cb(self, guid):
		self._cachers[guid] = False
		
	def rewrite_html(self, guid, html, ajax_url=None):
		soup = BeautifulSoup(html)
		img_tags = soup.findAll('img')
		
		if len(img_tags) == 0:
			return html
	
		mapping_file = os.path.join(self._store_location, guid, "mapping.pickle")
		if not os.path.isfile(mapping_file):
			if len(img_tags) > 0:
				#logging.warning("Should be downloaded images, but couldn't open mapping.  Recaching")
				self.cache_html(guid, html)
			return html
			
		try:
			mapping = open(mapping_file, 'r')
		except:
			logging.error("error opening cache pickle for guid %s %s" % (str(guid), mapping_file))
			return
		
		rewrite_hash = pickle.load(mapping)
		mapping.close()
	
		for result in img_tags:
			if rewrite_hash.has_key(result['src']):
				if rewrite_hash[result['src']][1] == UrlCacher.DOWNLOADED:
					if os.path.isfile(os.path.join(self._store_location, rewrite_hash[result['src']][0])):
						if ajax_url is None:
							result['src'] = "file://" + os.path.join(self._store_location, rewrite_hash[result['src']][0])
						else:
							result['src'] = ajax_url + "/cache/" + rewrite_hash[result['src']][0]
					else:
						logging.warning("file not found, not replacing")
						logging.debug("(should we attempt to recache here?")
				
		return soup.prettify()
		
	def remove_cache(self, guid):
		mapping_file = os.path.join(self._store_location, guid, "mapping.pickle")
		if not os.path.isfile(mapping_file):
			logging.warning("no mapping file, not deleting anything")
			return
			
		try:
			mapping = open(mapping_file, 'r')
		except:
			logging.error("error opening cache pickle for guid %s %s" % (str(guid), mapping_file))
			return
		
		rewrite_hash = pickle.load(mapping)
		mapping.close()
	
		os.remove(os.path.join(self._store_location, guid, "mapping.pickle"))
	
		for url in rewrite_hash.keys():
			try:
				os.remove(rewrite_hash[url][0])
			except:
				pass		
				
		try:
			os.rmdir(os.path.join(self._store_location, guid))
		except Exception, e:
			logging.warning("error removing image cache folder (not empty?) %s" % str(e))
		
	def finish(self):
		#logging.debug("OFFLINE IMAGE CACHE SHUTDOWN START")
		self._threadpool.joinAll(False, False)
		#logging.debug("OFFLINE IMAGE CACHE SHUTDOWN DONE")
		
class PageCacher:
	def __init__(self, guid, html, store_location, threadpool, finished_cb=None):
		self._guid = guid
		self._store_location = store_location
		self._threadpool = threadpool
		self._finished_cb = finished_cb
		
		self._soup = BeautifulSoup(html)
		self._cacher = UrlCacher(self._guid, self._store_location, self._threadpool, self._page_cached_cb)
		try:
			os.remove(os.path.join(self._store_location, self._guid, "mapping.pickle"))
		except:
			pass
		
	def process(self):
		# go through html and pull out images, feed them into cacher
		for result in self._soup.findAll('img'):
			self._cacher.queue_download(result['src'])
		self._cacher.start_downloads()
		
	def _page_cached_cb(self):
		rewrite_hash = self._cacher.get_rewrite_hash()
		try:
			mapping = open(os.path.join(self._store_location, self._guid, "mapping.pickle"), 'w')
		except:
			logging.error("error writing mapping %s" % os.path.join(self._store_location, self._guid, "mapping.pickle"))
			self._finished_cb(self._guid)
			return
		
		pickle.dump(rewrite_hash, mapping)
		mapping.close()
		self._finished_cb(self._guid)
		
class UrlCacher:
	FAIL = -1
	NOT_DOWNLOADED = 0
	DOWNLOADED = 1

	def __init__(self, guid, store_location, threadpool, finished_cb):
		self._guid = guid
		self._store_location = store_location
		self._threadpool = threadpool
		self._finished_cb = finished_cb
		self._cache_status = {}      #a dict of url: [localfile, status]
		self._dir_checked = False
		
	def queue_download(self, url):
		if self._cache_status.has_key(url):
			return
	
		md5 = hashlib.md5()
		md5.update(url)
		extension = os.path.splitext(url)[1]
		local_filename = os.path.join(self._guid, md5.hexdigest()) + extension
		
		if os.path.isfile(local_filename):
			#TODO: some sort of md5sum of the file?  or just assume it's ok?
			#urlretrieve probably guarantees success or it doesn't write the file
			self._cache_status[url] = [local_filename, UrlCacher.DOWNLOADED]
		else:
			self._cache_status[url] = [local_filename, UrlCacher.NOT_DOWNLOADED]
		
	def start_downloads(self):
		for url in self._cache_status.keys():
			if self._cache_status[url][1] != UrlCacher.DOWNLOADED:
				self._threadpool.queueTask(self._download_image, (url, self._cache_status[url][0]), self._download_complete)
		
	def get_rewrite_hash(self):
		return self._cache_status.copy()
	
	def _download_image(self, args):
		""" downloads an image at url, and stores it as local filename.
			threaded"""
		
		url, local_filename = args
		
		if not self._dir_checked:
			if not os.path.exists(os.path.join(self._store_location, self._guid)):
				try:
					os.makedirs(os.path.join(self._store_location, self._guid))
				except:
					pass
			self._dir_checked = True
		
		try:
			urllib.urlretrieve(url, os.path.join(self._store_location, local_filename))
		except:
			#TODO: any need to check if we have to delete half-dled file?
			return (url, False)
			
		return (url, True)
		
	@threaded_callback()
	def _download_complete(self, args):
		url, success = args
		if success:
			#logging.debug("Downloaded %s" % url)
			self._cache_status[url][1] = UrlCacher.DOWNLOADED
		else:
			#logging.debug("Failed to downloaded %s" % url)
			self._cache_status[url][1] = UrlCacher.FAIL
		
		self._check_finished()
			
	def _check_finished(self):
		for url in self._cache_status.keys():
			if self._cache_status[url][1] == UrlCacher.NOT_DOWNLOADED:
				return
		
		# does not guarantee success, just that we tried
		self._finished_cb()
