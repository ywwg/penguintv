# Synchronize entry read states with a server
import urllib
import urlparse
import threading
import logging
import sha
import traceback
import time
logging.basicConfig(level=logging.DEBUG)

import gobject

from ptvDB import FF_MARKASREAD
from amazon import articlesync_s3

### Debugging uses regular callbacks instead of gobject idlers
DEBUG = False

def threaded_func():
	def annotate(func):
		def _exec_cb(self, *args, **kwargs):
			if not kwargs.has_key('cb'):
				return func(self, *args, **kwargs)
			elif kwargs['cb'] is None:
				del kwargs['cb']
				return func(self, *args, **kwargs)
			
			def t_func(self, *args, **kwargs):
				cb = kwargs['cb']
				del kwargs['cb']
				retval = func(self, *args, **kwargs)
				if type(retval) is tuple:
					if DEBUG:
						cb(*retval)
					else:
						gobject.idle_add(cb, *retval)
				else:
					if DEBUG:
						cb(retval)
					else:
						gobject.idle_add(cb, retval)
				
			t = threading.Thread(None, t_func, "ArticleSync",
								 args=(self,) + args, kwargs=kwargs)
			t.setDaemon(True)
			t.start()
		return _exec_cb
	return annotate
	
def authenticated_func():
	def annotate(func):
		def _exec_cb(self, *args, **kwargs):
			logging.debug("authed?")
			if not self._enabled:
				logging.debug("not enabled")
				return
			elif self._conn is None:
				logging.debug("no connection")
				self.emit('server-error', "No Connection")
			elif not self._authenticated:
				logging.debug("not authed")
				self.emit('authentication-error', "Not authenticated")
			else:
				logging.debug("authed. calling: %s" % str(func))
				return func(self, *args, **kwargs)
		return _exec_cb
	return annotate	

class ArticleSync(gobject.GObject):

	__gsignals__ = {
		#'entries-viewed': (gobject.SIGNAL_RUN_FIRST, 
  #                         gobject.TYPE_NONE, 
  #                         ([gobject.TYPE_PYOBJECT])),
		#'entries-unviewed': (gobject.SIGNAL_RUN_FIRST, 
  #                         gobject.TYPE_NONE, 
  #                         ([gobject.TYPE_PYOBJECT])),
        'update-feed-count': (gobject.SIGNAL_RUN_FIRST, 
                           gobject.TYPE_NONE, 
                           ([gobject.TYPE_INT, gobject.TYPE_INT])),
        'got-readstates': (gobject.SIGNAL_RUN_FIRST, 
                           gobject.TYPE_NONE, 
                           ([gobject.TYPE_PYOBJECT])),
        'authentication-error': (gobject.SIGNAL_RUN_FIRST, 
                           gobject.TYPE_NONE, 
                           ([gobject.TYPE_PYOBJECT])),
        'server-error': (gobject.SIGNAL_RUN_FIRST, 
                           gobject.TYPE_NONE, 
                           ([gobject.TYPE_PYOBJECT]))             
	}

	def __init__(self, app, entry_view, username, password, enabled=True):
		gobject.GObject.__init__(self)
		global BUCKET_NAME, BUCKET_NAME_SUF
		if app is not None:
			app.connect('entry-updated', self._entry_updated_cb)
			app.connect('entries-viewed', self._entries_viewed_cb)
			
			self._db = app.db
		else:
			import ptvDB
			self._db = ptvDB.ptvDB()
		self._handlers = []
		
		if entry_view is not None:
			self.set_entry_view(entry_view)	
			
		self._conn = articlesync_s3.SyncClient(username, password)
		logging.debug("auth is false1")
		self._authenticated = False
		self._enabled = enabled		
		#diff is a dict of feed_id:readstates
		#and readstates is a dict of entry_id:readstate
		self._readstates_diff = {}
		self.__logging_in = False
		
		def update_cb(success):
			logging.debug("update was: %s" % str(success))
			return False
		gobject.timeout_add(30000, self.update_readstates, update_cb)
		
	def set_entry_view(self, entry_view):
		for disconnector, h_id in self._handlers:
			disconnector(h_id)
			
		h_id = entry_view.connect('entries-viewed', self._entries_viewed_cb)
		self._handlers.append((entry_view.disconnect, h_id))
	
	def set_enabled(self, enabled):
		self._enabled = enabled
		if not self._enabled:
			logging.debug("auth is false2")
			self._authenticated = False
		
	def set_username(self, username):
		self._conn.set_username(username)
	
	def set_password(self, password):
		self._conn.set_password(password)
		
	def is_authenticated(self):
		return self._authenticated
		
	def is_enabled(self):
		return self._enabled
		
	def is_working(self):
		my_threads = [t.getName() for t in threading.enumerate() \
			if t.getName().startswith("ArticleSync")]
			
		return len(my_threads)
		
	def finish(self, cb=None):
		last_diff = self._get_readstates_list(self._readstates_diff)
		self._readstates_diff = {}
		self._do_close_conn(last_diff, cb=cb)
	
	@threaded_func()
	def _do_close_conn(self, states):
		while self.is_working() > 1:
			print "self.is_working", self.is_working()
			time.sleep(.5)
		self._conn.finish(states)
		
	@threaded_func()
	def authenticate(self):
		"""Creates the bucket as part of authentication, helpfully"""
		if self.__logging_in:
			return False
		
		if self._authenticated:
			while self.is_working() > 1:
				print "self.is_working", self.is_working()
				time.sleep(.5)
			self._conn.finish()
			
		self.__logging_in = True
		result = self._conn.authenticate()
		self.__logging_in = False
		self._authenticated = result
		logging.debug("result of auth procedure: %s" % str(result))
		return result
		
	def _entries_viewed_cb(self, app, viewlist):
		for feed_id, viewlist in viewlist:
			for entry_id in viewlist:
				if not self._readstates_diff.has_key(feed_id):
					self._readstates_diff[feed_id] = {}
				self._readstates_diff[feed_id][entry_id] = 1
				
		logging.debug("sync updated diff: %s" % str(self._readstates_diff))
	
	def _entry_updated_cb(self, app, entry_id, feed_id):
		readstate = self._db.get_entry_read(entry_id)
		if not self._readstates_diff.has_key(feed_id):
			self._readstates_diff[feed_id] = {}
		self._readstates_diff[feed_id][entry_id] = readstate
		logging.debug("sync updated diff2: %s" % str(self._readstates_diff))
		
	@authenticated_func()	
	def update_readstates(self, cb):
		readstates = self._get_readstates_list(self._readstates_diff)
		self._readstates_diff = {}
		
		logging.debug("updating readstates: %s" % str(readstates))
		self._do_update_readstates(readstates, cb=cb)
		
	def _get_readstates_list(self, state_dict):
		read_entries = []
		unread_entries = []
		for feed_id in state_dict.keys():
			for entry_id in state_dict[feed_id].keys():
				if state_dict[feed_id][entry_id]:
					read_entries.append(entry_id)
				else:
					unread_entries.append(entry_id)
		read_hashes = self._db.get_hashes_for_entries(read_entries)
		readstates = [(r, 1) for r in read_hashes]
		return readstates
	
	@threaded_func()
	def _do_update_readstates(self, readstates):
		return self._conn.submit_readstates(readstates)
		
	@authenticated_func()
	def get_readstates_since(self, timestamp):
		logging.debug("getting readstates since %i" % timestamp)
		def get_readstates_cb(readstates):
			unread_hashes = []
			read_hashes = []
		
			for entry_hash, readstate in readstates:
				if readstate:
					read_hashes.append(entry_hash)
				else:
					unread_hashes.append(entry_hash)
					
			read_entries = self._db.get_entries_for_hashes(read_hashes)
			read_entries.sort()
			logging.debug("hash to entry conversion result:")
			for row in read_entries:
				logging.debug(str(row))
			viewlist = []
			cur_feed_id = None
			cur_list = []
			for feed_id, entry_id, readstate in read_entries:
				if feed_id != cur_feed_id:
					if len(cur_list) > 0:
						viewlist.append((cur_feed_id, cur_list))
						cur_list = []
					cur_feed_id = feed_id
				if readstate == 0:
					cur_list.append(entry_id)
				
			if len(cur_list) > 0:
				viewlist.append((cur_feed_id, cur_list))
				
			logging.debug("viewed shit: %s" % viewlist)
			self.emit('got-readstates', viewlist)
			return False
		
		self._do_get_readstates_since(timestamp, cb=get_readstates_cb)
			
	@threaded_func()
	def _do_get_readstates_since(self, timestamp):
		return self._conn.get_readstates_since(timestamp)
		
