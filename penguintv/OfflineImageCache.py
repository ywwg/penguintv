
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
import urlparse
import os.path
import pickle
import logging
import glob
import hashlib  #requires python2.5

import gobject

import utils
import ThreadPool
from BeautifulSoup.BeautifulSoup import BeautifulSoup

DEBUG = False

def guid_hash(guid):
	return str(hash(guid) % 20)

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
		guid = str(guid)
		if self._cachers.has_key(guid):
			if self._cachers[guid]:
				#logging.debug("that cacher is already active, ignoring, %s" % str(guid))
				return
			
		self._cachers[guid] = True
		page_cacher = PageCacher(guid, html, self._store_location, self._threadpool, self._cache_cb)
		
	def _cache_cb(self, guid):
		guid = str(guid)
		self._cachers[guid] = False
		
	def rewrite_html(self, guid, html=None, ajax_url=None):
		"""if we are not using ajax, then html is IGNORED and we go by the
		cached copy.  html is sometimes used to see if there should be a 
		cached copy at all, or if something goes wrong and we just need to
		return unaltered html
		"""
		
		guid = str(guid)
		cache_dir = os.path.join(self._store_location, guid_hash(guid))
		mapping_file = os.path.join(cache_dir, guid + "-" + "mapping.pickle")
		
		if not os.path.isfile(mapping_file):
			# quick and dirty check.  are there images?  if not, plain
			# html is fine
			if html.lower().find('<img') >= 0:
				#logging.warning("Should be downloaded images, but couldn't open mapping.  Recaching")
				self.cache_html(guid, html)
			return html
			
		try:
			mapping = open(mapping_file, 'r')
			rewrite_hash = pickle.load(mapping)
			non_ajax_html = pickle.load(mapping)
			mapping.close()
		except:
			logging.error("error opening cache pickle for guid %s %s" % (guid, mapping_file))
			logging.error("If you have upgraded penguintv, you might need to delete your image cache")
			return html
				
		if ajax_url is None:
			return non_ajax_html
			
		#else, rewrite on the fly
		soup = BeautifulSoup(html)
		img_tags = soup.findAll('img')
		
		if len(img_tags) == 0:
			return html
	
		for result in img_tags:
			# believe it or not, some img tags don't have a src, they have an id
			# that points to CSS.  At least I think that's what's going on
			if result.has_key('src'):
				if rewrite_hash.has_key(result['src']):
					if rewrite_hash[result['src']][1] == UrlCacher.DOWNLOADED:
						#if os.path.isfile(os.path.join(self._store_location, rewrite_hash[result['src']][0])):
						result['src'] = ajax_url + "/cache/" + rewrite_hash[result['src']][0]
						#else:
						#	logging.warning("file not found, not replacing")
						#	logging.debug("(should we attempt to recache here?")
				
		return soup.prettify()
		
	def remove_cache(self, guid):
		guid = str(guid)
		cache_dir = os.path.join(self._store_location, guid_hash(guid))
		mapping_file = os.path.join(cache_dir, guid + "-" + "mapping.pickle")
		
		if not os.path.isdir(cache_dir):
			# it was never cached I guess
			return
			
		if not os.path.isfile(mapping_file):
			# the dir exists, but not the file?
			#logging.warning("no mapping file, not deleting anything")
			return
			
		try:
			mapping = open(mapping_file, 'r')
		except:
			logging.error("error opening cache pickle for guid %s %s" % (guid, mapping_file))
			return
		
		rewrite_hash = pickle.load(mapping)
		mapping.close()
	
		os.remove(mapping_file)
	
		for url in rewrite_hash.keys():
			try:
				os.remove(os.path.join(self._store_location, rewrite_hash[url][0]))
			except Exception, e:
				logging.warning("error removing file: %s" % str(e))
				
		try:
			#os.rmdir(cache_dir)
			#utils.deltree(cache_dir)
			for f in glob.glob(os.path.join(cache_dir, guid + "-*")):
				os.remove(f)
		except Exception, e:
			#import glob
			logging.warning("error while removing image cache %s" % str(e))
			#logging.debug(glob.glob(os.path.join(cache_dir, "*")))
			#logging.debug(str(rewrite_hash))
		
	def finish(self):
		self._threadpool.joinAll(False, False)
		
class PageCacher:
	""" Take html and download all of the images to the store location.  Then
		process the html and rewrite the tags to point to these images.  The
		new html is then cached along with the image mapping in a pickle file.
		
		Note: this cached version of the html is only good for non-ajax use.
		In the case of ajax, the urls need to be rewritten on the fly
	"""
	def __init__(self, guid, html, store_location, threadpool, finished_cb=None):
		self._guid = str(guid)
		self._store_location = store_location
		self._threadpool = threadpool
		self._finished_cb = finished_cb
		self._soup = None
		
		self._cacher = UrlCacher(self._guid, self._store_location, self._threadpool, self._page_cached_cb)
		self._cache_dir = os.path.join(self._store_location, guid_hash(self._guid))
		try:
			os.remove(os.path.join(self._cache_dir, self._guid + "-" + "mapping.pickle"))
		except:
			pass
			
		self._threadpool.queueTask(self._get_soup, html, taskCallback=self.process)
		
	def _get_soup(self, html):
		return BeautifulSoup(html)
		
	def process(self, soup):
		# go through html and pull out images, feed them into cacher
		
		self._soup = soup

		for result in self._soup.findAll('img'):
			if result.has_key('src'):
				self._cacher.queue_download(result['src'])
		self._cacher.start_downloads()
		
	def _page_cached_cb(self):
		rewrite_hash = self._cacher.get_rewrite_hash()
		try:
			mapping = open(os.path.join(self._cache_dir, self._guid + "-" + "mapping.pickle"), 'w')
		except:
			logging.error("error writing mapping %s" % os.path.join(self._cache_dir, self._guid + "-" + "mapping.pickle"))
			self._finished_cb(self._guid)
			return
			
		img_tags = self._soup.findAll('img')
			
		for result in img_tags:
			# believe it or not, some img tags don't have a src, they have an id
			# that points to CSS.  At least I think that's what's going on
			if result.has_key('src'):
				if rewrite_hash.has_key(result['src']):
					if rewrite_hash[result['src']][1] == UrlCacher.DOWNLOADED:
						#if os.path.isfile(os.path.join(self._store_location, rewrite_hash[result['src']][0])):
						result['src'] = "file://" + os.path.join(self._store_location, rewrite_hash[result['src']][0])
						#	logging.warning("file not found, not replacing")
						#	logging.debug("(should we attempt to recache here?")
				
		non_ajax_html = self._soup.prettify()
		
		pickle.dump(rewrite_hash, mapping)
		pickle.dump(non_ajax_html, mapping)
		mapping.close()
		self._finished_cb(self._guid)
		
class UrlCacher:
	FAIL = -1
	NOT_DOWNLOADED = 0
	DOWNLOADED = 1

	def __init__(self, guid, store_location, threadpool, finished_cb):
		self._guid = str(guid)
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
		filename = urlparse.urlparse(url)[2]
		extension = os.path.splitext(filename)[1]
		local_filename = os.path.join(guid_hash(self._guid), self._guid + "-" + md5.hexdigest()) + extension
		
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
		cache_dir = os.path.join(self._store_location, guid_hash(self._guid))
		
		if not self._dir_checked:
			if not os.path.exists(cache_dir):
				try:
					os.makedirs(cache_dir)
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
