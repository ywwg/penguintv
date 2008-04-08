# Synchronize entry read states with a server
import urllib
import urlparse
import threading
import logging
import sha
import traceback
import time
import gettext
logging.basicConfig(level=logging.DEBUG)

_=gettext.gettext

import gobject
import gtk

from ptvDB import FF_MARKASREAD, STRING, INT
import utils

import amazon
import FtpSyncClient

### Debugging uses regular callbacks instead of gobject idlers
DEBUG = False

PLUGINS = {
	_("Amazon S3"): ("S3SyncClient", "S3SyncClient"),
	_("FTP"): ("FtpSyncClient", "FtpSyncClient")
	}

def threaded_func():
	def annotate(func):
		def _exec_cb(self, *args, **kwargs):
			if not kwargs.has_key('cb'):
				return func(self, *args, **kwargs)
			elif kwargs['cb'] is None:
				del kwargs['cb']
				return func(self, *args, **kwargs)
			
			def t_func(self, *args, **kwargs):
				self._operation_lock.acquire()
				cb = kwargs['cb']
				del kwargs['cb']
				try:
					retval = func(self, *args, **kwargs)
				except Exception, e:
					retval = None
					logging.error("Article Sync caught error: %s" % str(e))
				self._operation_lock.release()
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
	
def authenticated_func(defaultret=None):
	def annotate(func):
		def _exec_cb(self, *args, **kwargs):
			if not self._enabled:
				return defaultret
			elif self._conn is None:
				self.emit('server-error', "No Connection")
				return defaultret
			elif not self._authenticated:
				self.emit('authentication-error', "Not authenticated")
				return defaultret
			else:
				return func(self, *args, **kwargs)
		return _exec_cb
	return annotate	

class ArticleSync(gobject.GObject):

	__gsignals__ = {
		'update-feed-count': (gobject.SIGNAL_RUN_FIRST, 
                           gobject.TYPE_NONE, 
                           ([gobject.TYPE_INT, gobject.TYPE_INT])),
        'got-readstates': (gobject.SIGNAL_RUN_FIRST, 
                           gobject.TYPE_NONE, 
                           ([gobject.TYPE_PYOBJECT])),
		'sent-readstates': (gobject.SIGNAL_RUN_FIRST, 
                           gobject.TYPE_NONE, 
                           ([])),
        'authentication-error': (gobject.SIGNAL_RUN_FIRST, 
                           gobject.TYPE_NONE, 
                           ([gobject.TYPE_PYOBJECT])),
        'server-error': (gobject.SIGNAL_RUN_FIRST, 
                           gobject.TYPE_NONE, 
                           ([gobject.TYPE_PYOBJECT]))             
	}

	def __init__(self, app, entry_view, plugin, enabled=True, readonly=False):
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
			
		self._conn = None
		self._authenticated = False
		self._enabled = enabled		
		self._readonly = readonly
		#diff is a dict of feed_id:readstates
		#and readstates is a dict of entry_id:readstate
		self._readstates_diff = {}
		self._operation_lock = threading.Lock()
		
		self._current_plugin = None
		self.load_plugin(plugin)
		
		def update_cb(success):
			return False
		gobject.timeout_add(20 * 60 * 1000, self.get_and_send, update_cb)
		
	def set_entry_view(self, entry_view):
		for disconnector, h_id in self._handlers:
			disconnector(h_id)
			
		h_id = entry_view.connect('entries-viewed', self._entries_viewed_cb)
		self._handlers.append((entry_view.disconnect, h_id))
	
	def set_enabled(self, enabled):
		if self._conn is None:
			return
		if self._enabled and self._authenticated and not enabled:
			#changing to offline
			self.finish()
		self._enabled = enabled
		if not self._enabled:
			self._authenticated = False
			
	def set_readonly(self, readonly):
		self._readonly = readonly
		if self._conn is not None:
			self._conn.set_readonly(readonly)
			
	def get_current_plugin(self):
		return self._current_plugin
			
	def get_plugins(self):
		#will eventually be generated automatically
		return PLUGINS
			
	def get_parameter_ui(self, plugin):
		if self._conn is None:
			#logging.debug("no conn, returning")
			return None
		if plugin != self._current_plugin:
			#logging.debug("wrong plugin, returning: %s %s" % (plugin, self._current_plugin))
			return None
		for title in PLUGINS.keys():
			if title == plugin:
				return self._build_ui(plugin, self._conn.get_parameters())
		#logging.debug("didn't find plugin, returning")
		return None
	
	def _build_ui(self, plugin, parameters):
		table = gtk.Table(2, len(parameters), False)
		y = 0
		for label_text, param, default, hidechars in parameters:
			label = gtk.Label(label_text)
			label.set_alignment(0, 0.5)
			table.attach(label, 0, 1, y, y + 1)
			entry = gtk.Entry()
			entry.set_visibility(not hidechars)
			table.attach(entry, 1, 2, y, y + 1)
			self._setup_entry(plugin.replace('_',''), entry, param, default)
			y += 1
		return table
		
	def _setup_entry(self, plugin, widget, param, default):
		if utils.HAS_GCONF:
			try:
				import gconf
			except:
				from gnome import gconf
				
			conf = gconf.client_get_default()
			conf.add_dir('/apps/penguintv',gconf.CLIENT_PRELOAD_NONE)
			conf.notify_add('/apps/penguintv/sync_plugins/%s/%s' % \
				(plugin.replace(' ', '_'), param),
				self._gconf_param_changed, (widget, plugin, param))
		value = self._db.get_setting(STRING, '/apps/penguintv/sync_plugins/%s/%s' % \
				(plugin.replace(' ', '_'), param), default)
		widget.set_text(value)
		widget.connect('changed', self._parameter_changed, plugin, param)
	
	def _gconf_param_changed(self, c, connid, entr, (widget, plugin, param)):	
		self._parameter_changed(widget, plugin, param, noset=True)
			
	def _parameter_changed(self, widget, plugin, param, noset=False):
		if not noset:
			self._db.set_setting(STRING, '/apps/penguintv/sync_plugins/%s/%s' % \
				(plugin.replace(' ', '_'), param), widget.get_text())
			
		getattr(self._conn, 'set_%s' % param)(widget.get_text())
		
	def load_plugin(self, plugin=None):
		if plugin is None:
			if self._current_plugin is None:
				return
			plugin = self._current_plugin
			
		self._authenticated = False
			
		def _do_load_plugin():
			if self.is_working() > 1:
				return True
				
			self._operation_lock.acquire()
			self._current_plugin = plugin
			for title in PLUGINS.keys():
				if title == plugin:
					self._conn = getattr(__import__(PLUGINS[title][0]), PLUGINS[title][1])()
					self._conn.set_readonly(self._readonly)
					self._load_plugin_settings(plugin)
					self._operation_lock.release()
					return False
			self._conn = None
			self._operation_lock.release()
			return False
			
		if self._current_plugin is not None:
			self.finish()
			gobject.timeout_add(500, _do_load_plugin)
		else:
			_do_load_plugin()
			
			
	def _load_plugin_settings(self, plugin):
		assert self._conn is not None
		
		for label, param, default, hidechars in self._conn.get_parameters():
			val = self._db.get_setting(STRING, '/apps/penguintv/sync_plugins/%s/%s' % \
					(plugin.replace(' ', '_'), param), default)
			#logging.debug("initializing plugin %s with %s" % (param, val))
			getattr(self._conn, 'set_%s' % param)(val)
			
	def is_authenticated(self):
		return self._authenticated
		
	def is_enabled(self):
		return self._enabled
		
	def is_working(self):
		my_threads = [t.getName() for t in threading.enumerate() \
			if t.getName().startswith("ArticleSync")]
			
		return len(my_threads)
		
	def is_loaded(self):
		return self._conn is not None
		
	def finish(self):
		def empty_cb(arg=None):
			pass
			
		if self._enabled and self._conn is not None:
			last_diff = self._get_readstates_list(self._readstates_diff)
			self._readstates_diff = {}
			conn = self._conn
			self._conn = None
			self._do_close_conn(conn, last_diff, cb=empty_cb)
	
	@threaded_func()
	def _do_close_conn(self, conn, states):
		while self.is_working() > 1:
			time.sleep(.5)
		conn.finish(states)
		
	@threaded_func()
	def authenticate(self):
		"""Creates the bucket as part of authentication, helpfully"""
		if self._conn is None:
			return False
		
		if self._authenticated:
			while self.is_working() > 1:
				time.sleep(.5)
			self._conn.finish()
			
		result = self._conn.authenticate()
		self._authenticated = result
		return result
		
	def disconnected(self):
		"""lost the connection -- no way to shut down"""
		self._authenticated = False
		
	def _entries_viewed_cb(self, app, viewlist):
		if not self._authenticated:
			return
		for feed_id, viewlist in viewlist:
			for entry_id in viewlist:
				if not self._readstates_diff.has_key(feed_id):
					self._readstates_diff[feed_id] = {}
				self._readstates_diff[feed_id][entry_id] = 1
				
		#logging.debug("sync updated diff: %s" % str(self._readstates_diff))
	
	def _entry_updated_cb(self, app, entry_id, feed_id):
		if not self._authenticated:
			return
		readstate = self._db.get_entry_read(entry_id)
		if not self._readstates_diff.has_key(feed_id):
			self._readstates_diff[feed_id] = {}
		self._readstates_diff[feed_id][entry_id] = readstate
		#logging.debug("sync updated diff2: %s" % str(self._readstates_diff))
		
	@authenticated_func(True)
	def get_and_send(self, cb):
		timestamp = self._db.get_setting(INT, 'article_sync_timestamp', int(time.time()) - (60 * 60 * 24))
		self.get_readstates_since(timestamp)
		if self._readonly:
			logging.info("Readonly mode, not submitting")
		else:
			self.submit_readstates()
		return True
	
	@authenticated_func()
	def submit_readstates_since(self, timestamp, cb):
		if self._readonly:
			logging.info("Readonly mode, not submitting")
			return
			
		readstates = self._db.get_entries_since(timestamp)
		readstates = [(r[2],r[3]) for r in readstates if r[3] == 1]
		logging.debug("submitting readstates since %i, there are %i" \
			% (timestamp, len(readstates)))
		self._do_submit_readstates(readstates, cb=cb)
		
	@authenticated_func()	
	def submit_readstates(self):
		if self._readonly:
			logging.info("Readonly mode, not submitting")
			return
			
		def submit_cb(success):
			self.emit('server-error', 'Problem submitting readstates')
			return False
	
		readstates = self._get_readstates_list(self._readstates_diff)
		self._readstates_diff = {}
		
		logging.debug("updating %i readstates" % len(readstates))
		self._do_submit_readstates(readstates, cb=submit_cb)
		return True
		
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
	def _do_submit_readstates(self, readstates):
		return self._conn.submit_readstates(readstates)
		
	@authenticated_func()
	def get_readstates_since(self, timestamp):
		logging.debug("getting readstates since %i" % timestamp)
		self._do_get_readstates_since(timestamp, cb=self.get_readstates_cb)
			
	@threaded_func()
	def _do_get_readstates_since(self, timestamp):
		return self._conn.get_readstates_since(timestamp)
		
	@authenticated_func()
	def get_readstates(self, hashlist):
		if len(hashlist) == 0:
			return
		logging.debug("getting readstates for %i entries" % len(hashlist))	
		self._do_get_readstates(hashlist, cb=self.get_readstates_cb)
		
	@authenticated_func()
	def get_readstates_for_entries(self, entrylist):
		"""take an entrylist, build a list of hashes, ask for their readstates"""
		
		if len(entrylist) == 0:
			return
			
		logging.debug("getting %i readstates" % len(entrylist))
		
		hashlist = self._db.get_hashes_for_entries(entrylist)
		self._do_get_readstates(hashlist, cb=self.get_readstates_cb)
		
	@threaded_func()
	def _do_get_readstates(self, hashlist):
		return self._conn.get_readstates(hashlist)
		
	def get_readstates_cb(self, readstates):
		if len(readstates) == 0:
			logging.debug("No readstates to report")
			self.emit('got-readstates', [])
			return False
			
		unread_hashes = []
		read_hashes = []
	
		for entry_hash, readstate in readstates:
			if readstate:
				read_hashes.append(entry_hash)
			else:
				unread_hashes.append(entry_hash)
				
		unread_entries = \
			self._db.get_entries_for_hashes(read_hashes)
		unread_entries.sort()
		logging.debug("hash to entry conversion result: %i known %i unknown" \
			% (len(unread_entries), len(readstates) - len(unread_entries)))
		viewlist = []
		cur_feed_id = None
		cur_list = []
		for feed_id, entry_id, readstate in unread_entries:
			if feed_id != cur_feed_id:
				if len(cur_list) > 0:
					viewlist.append((cur_feed_id, cur_list))
					cur_list = []
				cur_feed_id = feed_id
			if readstate == 0:
				cur_list.append(entry_id)
			#else:
			#	logging.debug("programming error: should never be true")
			
		if len(cur_list) > 0:
			viewlist.append((cur_feed_id, cur_list))
			
		logging.debug("marking %i as viewed" % len(viewlist))
		self.emit('got-readstates', viewlist)
		return False
		
