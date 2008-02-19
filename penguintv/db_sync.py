# Synchronize entry read states with a server
import urllib
import urlparse
import threading
import logging
import sha
logging.basicConfig(level=logging.DEBUG)

import gobject

URL_URL = "http://penguintv.sourceforge.net/sync_server.txt"

def threaded_func():
	def annotate(func):
		def _exec_cb(self, *args, **kwargs):
			t = threading.Thread(None, func, 
								 args=(self,) + args, kwargs=kwargs)
			t.start()
		return _exec_cb
	return annotate
	
def authenticated_func():
	def annotate(func):
		def _exec_cb(self, *args, **kwargs):
			if not _enabled:
				return
			elif self._serveraddr is None:
				self.emit('server-error', "Server address unknown")
			elif not self._authenticated:
				self.emit('authentication-error', "Not authenticated")
			else:
				return func(self, *args, **kwargs)
		return _exec_cb
	return annotate	

class db_sync(gobject.GObject):

	__gsignals__ = {
		'entries-viewed': (gobject.SIGNAL_RUN_FIRST, 
                           gobject.TYPE_NONE, 
                           ([gobject.TYPE_INT, gobject.TYPE_PYOBJECT])),
		'entries-unviewed': (gobject.SIGNAL_RUN_FIRST, 
                           gobject.TYPE_NONE, 
                           ([gobject.TYPE_INT, gobject.TYPE_PYOBJECT])),
        'authentication-error': (gobject.SIGNAL_RUN_FIRST, 
                           gobject.TYPE_NONE, 
                           ([gobject.TYPE_PYOBJECT])),
        'server-error': (gobject.SIGNAL_RUN_FIRST, 
                           gobject.TYPE_NONE, 
                           ([gobject.TYPE_PYOBJECT])),
	}

	def __init__(self, app, entry_view, username, password):
		app.connect('feed-polled', self._feed_polled_cb)
		app.connect('entry-updated', self._entry_updated_cb)
			
		self._db = app.db
		self._handlers = []
		
		self.set_entry_view(entry_view)	
			
		self._username = username
		self._password = password
		self._serveraddr = None
		self._authenticated = False
		self._enabled = True
		
		def authenticated_cb(success):
			self._authenticated = success
			return False

		def server_addr_cb(addr):
			self._serveraddr = addr
			self._authenticate(authenticated_cb)
			return False
		self._get_server_url(server_addr_cb)
		
	def set_entry_view(self, entry_view):
		for disconnector, h_id in self._handlers:
			disconnector(h_id)
			
		h_id = entry_view.connect('entries-viewed', self._entries_viewed_cb)
		self._handlers.append((entry_view.disconnect, h_id))
	
	def set_enabled(self, enabled):
		self._enabled = enabled
		
	def is_authenticated(self):
		return self._authenticated
	
	@authenticated_func()	
	def _feed_polled_cb(self, feed_id, update_data):
		def _get_readstates_cb(server_readstates):
			if server_readstates is None:
				return False
		
			# for items that are different from default
			apply_list = [r[0] for r in server_readstates \
							if r[1] != default_read]
						
			# apply them
			signal_name = default_read and 'entries-unviewed' or 'entries-viewed'
			self.emit(signal_name, feed_id, apply_list)
		
			# build a list of everything not on the server
			submit_list = [e_id for e_id in idlist \
							if e_id not in server_readstates.keys()]
		
			# submit the default
			self.submit_readstates(submit_list, default_read, 
									self._error_cb)
			return False
		id_list = update_data['new_entryids']
		
		# what's the default?
		default_read = self._db.get_flags_for_feed(feed_id) & FF_MARKASREAD
		
		#get readstates in a thread, call back with result
		self.get_readstates(id_list, _get_readstates_cb, self._error_cb)
		
	@authenticated_func()
	def _entries_viewed_cb(self, o, feed_id, entrylist):
		# Update the server with the new readstates
		id_list = [e['entry_id'] for e in entrylist]
		self.submit_readstates(id_list, True, self._error_cb)
	
	@authenticated_func()	
	def _entry_updated_cb(self, app, entry_id, feed_id):
		readstate = self._db.get_entry_read(entry_id)
		self.submit_readstates([entry_id], readstate, self._error_cb)
		
	def _error_cb(self, errtype, errmsg):
		logging.debug("error: %i %s" % (errtype, errmsg))
		if errtype == 0:
			self.emit('authentication-error', errmsg)
		else:
			self.emit('server-error', errmsg)
		return False
		
	@authenticated_func()
	@threaded_func()
	def get_readstates(self, id_list, cb, error_cb):
		"""Called from a separate thread to avoid blocking.  Returns
		a dictionary with mapping entry_id: readstate.  Or returns 
		None on failure"""
		
		readstates = []
		
		hashes = self._get_entryhashes(id_list)
		
		for e_id in id_list:
			try:
				fd = urllib.urlopen('http://%s:%s@%s/get_readstates?entryhash=%s' 
					% (self._username, self._password, 
					   self._serveraddr, hashes[e_id]))
			
				readstate = int(fd.readline())
				readstates.append((entry_id, readstate))	
			except ValueError, e:
				gobject.idle_add(error_cb, 1, str(e))
				gobject.idle_add(cb, None)
				return
			except IOError, e:
				if e[1] == 401:
					gobject.idle_add(error_cb, 0, str(e))
				else:
					gobject.idle_add(error_cb, 1, str(e))
				gobject.idle_add(cb, None)
				return
		
		gobject.idle_add(cb, readstates)
		
	@authenticated_func()
	@threaded_func()
	def submit_readstates(self, id_list, readstate, error_cb):
		"""Called from a separate thread to avoid blocking.  Returns
		True on success, False on failure"""
		try:
			hashes = self._get_entryhashes(id_list)
			
			for e_id in id_list:				
				urllib.urlopen('http://%s:%s@%s/set_readstates?entryhash=%s&readstate=%s'
					% (self._username, self._password, self._serveraddr,
					   hashes[e_id], readstate))
		except Exception, e:
			gobject.idle_add(error_cb, errtype, errmsg)
			
	@threaded_func()
	def _authenticate(self, cb):
		try:
			fd = urllib.urlopen('http://%s:%s@%s/ping' % (self._username, 
								self._password, self._serveraddr))
			cb(True)
		except IOError, e:
			logging.debug("error: %s" % str(e))
			if e[1] == 401:
				logging.debug("not authorized")
			cb(False)
		
	@threaded_func()
	def _get_server_url(self, cb):
		fd = urllib.urlopen(URL_URL)
		url = fd.readline().split('\n')[0]
		parsed = urlparse.urlparse(url)
		if parsed[0] != "http":
			gobject.idle_add(cb, None)
		else:
			addr = "%s%s" % (parsed[1], parsed[2])
			gobject.idle_add(cb, addr)
		
	def _get_entryhashes(self, id_list):
		entries = self._db.get_entry_block(id_list)
		hashes = {}
		s = sha.new()
		for entry in entries:
			s.update(entry['guid'] + entry['title'])
			hashes[entry['entry_id']] = s.hexdigest()
		return hashes
