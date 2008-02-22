# Synchronize entry read states with a server
import urllib
import urlparse
import threading
import logging
import sha
logging.basicConfig(level=logging.DEBUG)

import gobject

from ptvDB import FF_MARKASREAD

URL_URL = "http://penguintv.sourceforge.net/sync_server.txt"

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
				
			t = threading.Thread(None, t_func, 
								 args=(self,) + args, kwargs=kwargs)
			t.setDaemon(True)
			t.start()
		return _exec_cb
	return annotate
	
def authenticated_func():
	def annotate(func):
		def _exec_cb(self, *args, **kwargs):
			if not self._enabled:
				return
			elif self._serveraddr is None:
				self.emit('server-error', "Server address unknown")
			elif not self._authenticated:
				self.emit('authentication-error', "Not authenticated")
			else:
				return func(self, *args, **kwargs)
		return _exec_cb
	return annotate	

class ArticleSync(gobject.GObject):

	__gsignals__ = {
		'entries-viewed': (gobject.SIGNAL_RUN_FIRST, 
                           gobject.TYPE_NONE, 
                           ([gobject.TYPE_INT, gobject.TYPE_PYOBJECT])),
		'entries-unviewed': (gobject.SIGNAL_RUN_FIRST, 
                           gobject.TYPE_NONE, 
                           ([gobject.TYPE_INT, gobject.TYPE_PYOBJECT])),
        'update-feed-count': (gobject.SIGNAL_RUN_FIRST, 
                           gobject.TYPE_NONE, 
                           ([gobject.TYPE_INT, gobject.TYPE_INT])),
        'authentication-error': (gobject.SIGNAL_RUN_FIRST, 
                           gobject.TYPE_NONE, 
                           ([gobject.TYPE_PYOBJECT])),
        'server-error': (gobject.SIGNAL_RUN_FIRST, 
                           gobject.TYPE_NONE, 
                           ([gobject.TYPE_PYOBJECT]))             
	}

	def __init__(self, app, entry_view, username, password, enabled=True):
		gobject.GObject.__init__(self)
		if app is not None:
			app.connect('feed-polled', self._feed_polled_cb)
			app.connect('entry-updated', self._entry_updated_cb)
			
			self._db = app.db
		else:
			import ptvDB
			self._db = ptvDB.ptvDB()
		self._handlers = []
		
		if entry_view is not None:
			self.set_entry_view(entry_view)	
			
		self._username = username
		self._password = password
		self._serveraddr = None
		self._authenticated = False
		self._enabled = enabled		
		self.__logging_in = False
		self.__urllib_lock = threading.Lock()
		
	def set_entry_view(self, entry_view):
		for disconnector, h_id in self._handlers:
			disconnector(h_id)
			
		h_id = entry_view.connect('entries-viewed', self._entries_viewed_cb)
		self._handlers.append((entry_view.disconnect, h_id))
	
	def set_enabled(self, enabled):
		self._enabled = enabled
		
	def set_username(self, username):
		self._username = username
	
	def set_password(self, password):
		self._password = password
		
	def is_authenticated(self):
		return self._authenticated
		
	def is_enabled(self):
		return self._enabled
		
	@threaded_func()
	def authenticate(self):
		if self.__logging_in:
			return False
			
		self.__logging_in = True
		if self._serveraddr is None:
			self._serveraddr = self._get_server_url()
			if self._serveraddr is None:
				self.emit('server-error', "Couldn't get server address")
				self._authenticated = False
				self.__logging_in = False
				return False
		try:
			self.__urllib_lock.acquire()
			fd = urllib.urlopen('http://%s:%s@%s/ping' % (self._username, 
								self._password, self._serveraddr))
			self.__urllib_lock.release()
			self._authenticated = True
			self.__logging_in = False
			return True
		except IOError, e:
			self.__urllib_lock.release()
			logging.debug("error: %s" % str(e))
			if e[1] == 401:
				logging.debug("not authorized")
			self._authenticated = False
			self.__logging_in = False
			return False
		except Exception, e:
			logging.debug("eh2? %s" % str(e))
			self.__urllib_lock.release()
			return False
		
	@threaded_func()
	def _get_server_url(self):
		for i in range(0,3):
			try:
				self.__urllib_lock.acquire()
				fd = urllib.urlopen(URL_URL)
				self.__urllib_lock.release()
				break
			except IOError, e:
				self.__urllib_lock.release()
				logging.debug("getting server url io error, ignoring: %s" % \
									str(e))
				fd = None
			except Exception, e:
				logging.debug("eh? %s" % str(e))
				self.__urllib_lock.release()
		if fd is None:
			return None
		url = fd.readline().split('\n')[0]
		parsed = urlparse.urlparse(url)
		if parsed[0] != "http":
			return None
		else:
			addr = "%s%s" % (parsed[1], parsed[2])
			return addr
	
	@authenticated_func()	
	def _feed_polled_cb(self, app, feed_id, update_data):
		if not update_data.has_key('new_entryids'):
			return
		id_list = update_data['new_entryids']
		
		#print "new entry ids!", id_list
		
		if len(id_list) == 0:
			return
		
		#get readstates in a thread, call back with result
		self.get_readstates(id_list, 
					cb=self._get_readstates_cb)
		
	@authenticated_func()
	def _entries_viewed_cb(self, app, feed_id, entrylist):
		pass
		## Update the server with the new readstates
		#state_list = [(e['entry_id'], True) for e in entrylist]
		#self.submit_readstates(state_list, cb=self._error_cb)
	
	@authenticated_func()	
	def _entry_updated_cb(self, app, entry_id, feed_id):
		pass
		#readstate = self._db.get_entry_read(entry_id)
		#self.submit_readstates([(entry_id,readstate)], cb=self._error_cb)
		
	def _error_cb(self, errtype, errmsg):
		if errtype is None:
			return False
		logging.debug("error: %s --  %s" % (str(errtype), errmsg))
		if errtype == 0:
			self.emit('authentication-error', errmsg)
		else:
			self.emit('server-error', errmsg)
		return False
		
	@authenticated_func()
	def get_readstates(self, id_list=None, timestamp=None, cb=None):
		"""get hashes while we are in main thread"""
		
		assert id_list is not None or timestamp is not None
		if cb is None:
			cb = self._get_readstates_cb
		
		if id_list is None:
			hashes = None
		else:
			hashes = self._get_entryhashes(id_list)
		self._do_get_readstates(hashes, timestamp, 
							cb=cb)
		
	@threaded_func()
	def _do_get_readstates(self, hashes=None, timestamp=None):
		"""takes dict of entry:hashes and/or a timestamp"""
		
		readstates = {}
		if timestamp is not None:
			if hashes is not None:
				base_url = 'http://%s:%s@%s/get_readstates?timestamp=%s&entryhashes=' \
							% (self._username, self._password, 
								self._serveraddr, timestamp)
			else:
				base_url = 'http://%s:%s@%s/get_readstates?timestamp=%s' \
							% (self._username, self._password, 
								self._serveraddr, timestamp)
		else:
			base_url = 'http://%s:%s@%s/get_readstates?entryhashes=' \
						% (self._username, self._password, self._serveraddr)
					
		hash_csv = ''
		
		def build_readstates(h_csv):
			readstates = {}
			try:
				logging.debug("getting: %s" % (base_url + h_csv))
				self.__urllib_lock.acquire()
				fd = urllib.urlopen(base_url + h_csv)
				self.__urllib_lock.release()
				for line in fd.readlines():
					entryhash, readstate = line.split(' ')
					readstate = readstate.split('\n')[0]
					readstates[entryhash] = int(readstate)
				return readstates
			except ValueError, e:
				self.__urllib_lock.release()
				self.emit('server-error', str(e))
				return {}
			except IOError, e:
				self.__urllib_lock.release()
				if e[1] == 401:
					self.emit('authentication-error', str(e))
				else:
					self.emit('server-error', str(e))
				return {}
		
		if hashes is not None:
			self._submit_list(base_url, hashes)
			for e_id in hashes.keys():
				if len(base_url) + len(hash_csv) + len(hashes[e_id]) > 4000:
					readstates.update(build_readstates(hash_csv[:-1]))
					hash_csv = ''
				hash_csv += str(hashes[e_id]) + ','
				
			if len(hash_csv) > 0:
				readstates.update(build_readstates(hash_csv[:-1]))
		else:
			readstates.update(build_readstates(''))
		
		return readstates
		
	def _get_readstates_cb(self, server_readstates):
		"""takes a dict of hashed_entry:readstate"""
		if server_readstates is None:
			return False
			
		def emit_signal(signal_name, feed_id, entrylist,):
			logging.debug("would emit %s with %s %s" % 
				(signal_name, feed_id, entrylist))
			self.emit(signal_name, feed_id, entrylist)
				
		unhashed_readstates = []
		for k in server_readstates.keys():
			f_id, e_id = self._db.get_entry_for_hash(k)
			if e_id is not None:
				unhashed_readstates.append((f_id, e_id, server_readstates[k]))
			
		# sort by feed id
		unhashed_readstates.sort()
		cur_feed_id = None
		cur_list = []
		for feed_id, entry_id, readstate in unhashed_readstates:
			if cur_feed_id != feed_id:
				if len(cur_list) > 0:
					default_read = self._db.get_flags_for_feed(cur_feed_id) & \
						FF_MARKASREAD and 1 or 0
					title = self._db.get_feed_title(cur_feed_id)
					logging.debug("SYNC: %s %s" % (title, str(cur_list)))	
					emit_list = [e[0] for e in cur_list if e[1] != default_read]
				
					# what's the default?
					signal_name = default_read and \
						'entries-unviewed' or 'entries-viewed'
					emit_signal(signal_name, cur_feed_id, emit_list)
					
				cur_feed_id = feed_id
			cur_list.append((entry_id, readstate))
		if len(cur_list) > 0:
			default_read = self._db.get_flags_for_feed(cur_feed_id) & \
				FF_MARKASREAD and 1 or 0
			title = self._db.get_feed_title(cur_feed_id)
			logging.debug("SYNC: %s %s" % (title, str(cur_list)))	
			emit_list = [e[0] for e in cur_list if e[1] != default_read]
			signal_name = default_read and \
				'entries-unviewed' or 'entries-viewed'
			emit_signal(signal_name, feed_id, emit_list)

		return False
		
	@authenticated_func()
	def submit_readstates(self, state_list, cb=None):
		"""state list is a list of (entry_id, readstate)"""
		#get hashes while we are in main thread
		
		id_list = [r[0] for r in state_list]
		hashes = self._get_entryhashes(id_list)
		hash_dict = {}
		for entry_id, readstate in id_list:
			hash_dict[hashes[entry_id]] = readstate
		if cb is None:
			return (self._do_submit_readstates(hash_dict))
		else:
			self._do_submit_readstates(hash_dict, cb=cb)
			
	@authenticated_func()
	def submit_readstates_since(self, timestamp, cb=None):
		hashlist = self._db.get_entries_since(timestamp)
		
		hashlist.sort()
		cur_feed_id = None
		cur_list = []
		for feed_id, entry_id, entry_hash, read in hashlist:
			if cur_feed_id != feed_id:
				if len(cur_list) > 0:
					default_read = self._db.get_flags_for_feed(cur_feed_id) & \
							FF_MARKASREAD and 1 or 0
					changed = {}
					for entry_id, readstate in cur_list:
						if readstate != default_read:
							changed[entry_id] = readstate
					self._do_submit_readstates(changed, cb=cb)
				cur_feed_id = feed_id
			cur_list.append((entry_hash, read))
		if len(cur_list) > 0:
			default_read = self._db.get_flags_for_feed(cur_feed_id) & \
				FF_MARKASREAD and 1 or 0
			changed = {}
			for entry_id, readstate in cur_list:
				if readstate != default_read:
					changed[entry_id] = readstate
			self._do_submit_readstates(changed, cb=cb)
		
	@threaded_func()		
	def _do_submit_readstates(self, hashes):
		"""hashes is a dict of entry_hashes."""
	
		def _submit(read_list, unread_list):
			failure = False
			base_url = 'http://%s:%s@%s/set_readstates?readstate=1&entryhashes=' % \
					(self._username, self._password, self._serveraddr)
			if not self._submit_list(base_url, read_list):
				failure = True
			base_url = 'http://%s:%s@%s/set_readstates?readstate=0&entryhashes=' % \
					(self._username, self._password, self._serveraddr)
			if not self._submit_list(base_url, unread_list):
				failure = True
			return not failure
			
		read_list = []
		unread_list = []
		for e_hash in hashes.keys():
			if hashes[e_hash]:
				read_list.append(e_hash)
			else:
				unread_list.append(e_hash)
		return _submit(read_list, unread_list)
			
	@authenticated_func()
	def submit_feed_counts(self, feed_dict, cb=None):
		hash_dict = {}
		for feed_id in feed_dict.keys():
			url = self._db.get_feed_info(feed_id)['url']
			s = sha.new()
			s.update(url)			
			hash_dict[s.hexdigest()] = feed_dict[feed_id]
			
		#logging.debug("feed hashes: %s" % str(hash_dict))
			
		self._do_submit_feed_counts(hash_dict, cb=cb)
		
	@threaded_func()
	def _do_submit_feed_counts(self, hash_dict):
		try:
			base_url = 'http://%s:%s@%s/set_feedcounts?' % \
					(self._username, self._password, self._serveraddr)
					
			hashes = '&hashes='
			counts = '&counts='
			
			for feedhash in hash_dict.keys():
				if len(base_url) + len(hashes) + len(counts) >= 4000:
					self.__urllib_lock.acquire()
					urllib.urlopen(''.join((base_url, hashes[:-1], counts[:-1])))
					self.__urllib_lock.release()
					hashes = '&hashes='
					counts = '&counts='
				hashes += feedhash + ','
				counts += str(hash_dict[feedhash]) + ','
			if len(hashes) > len('&hashes='):
				self.__urllib_lock.acquire()
				urllib.urlopen(''.join((base_url, hashes[:-1], counts[:-1])))
				self.__urllib_lock.release()
			return True
		except Exception, e:
			logging.debug("Error: %s" % str(e))
			return False
			
	@authenticated_func()
	def get_feed_counts(self, cb=None):
		if cb is None:
			cb = _get_feed_counts_cb
			feed_dict = {}
			for feed_id, title, url in self._db.get_feedlist():
				s = sha.new()
				s.update(url)
				feed_dict[s.hexdigest()] = feed_id
			
		def _get_feed_counts_cb(counts):
			for feedhash in counts.keys():
				try:
					logging.debug("emit update-feed-count: %i %i" % \
						(feed_dict[feedhash], counts[feedhash]))
					self.emit('update-feed-count', 
						feed_dict[feedhash], counts[feedhash])
				except:
					logging.debug("got key from server that doesn't exist locally -- this is ok")
			return False

		self._do_get_feed_counts(cb=cb)
	
	@threaded_func()
	def _do_get_feed_counts(self):
		"""Called from a separate thread to avoid blocking.  Returns
		a dictionary with mapping entry_id: readstate.  Or returns 
		None on failure"""
		
		counts = {}
		try:
			#logging.debug("getting: %s" % (base_url + h_csv))
			self.__urllib_lock.acquire()
			fd = urllib.urlopen('http://%s:%s@%s/get_feedcounts' \
					% (self._username, self._password, self._serveraddr))
			self.__urllib_lock.release()
			for line in fd.readlines():
				feedhash, count = line.split(' ')
				count = count.split('\n')[0]
				counts[feedhash] = int(count)
			return counts
		except ValueError, e:
			self.__urllib_lock.release()
			self.emit('server-error', str(e))
			return {}
		except IOError, e:
			self.__urllib_lock.release()
			if e[1] == 401:
				self.emit('authentication-error', str(e))
			else:
				self.emit('server-error', str(e))
			return {}
	
		return counts
		
	def _get_entryhashes(self, id_list):
		""""""
		entries = self._db.get_entry_block(id_list)
		hashdict = {}
		for entry in entries:
			if entry['hash'] is not None:
				hashdict[entry['entry_id']] = entry['hash']
			else:
				logging.error("Hash does not exist for entry: %s" % \
					str(entry['entry_id']))
				#This must match ptvdb line ~1565
				#s = sha.new()
				#s.update(str(entry['guid']) + str(entry['title']))
				#hashdict[entry['entry_id']] = s.hexdigest()
		return hashdict
		
	def _submit_list(self, base_url, arglist):
		try:
			hash_str = ''
			for arg in arglist:
				if len(base_url) + len(hash_str) >= 4000:
					self.__urllib_lock.acquire()
					urllib.urlopen(base_url + hash_str[:-1])
					self.__urllib_lock.release()
					hash_str = ''
				hash_str += str(arg) + ','
			if len(hash_str) > 0:
				self.__urllib_lock.acquire()
				urllib.urlopen(base_url + hash_str[:-1])
				self.__urllib_lock.release()
			return True
		except Exception, e:
			logging.warning("submission error: %s %s, %s" % \
				(base_url, arglist, str(e)))
			return False
