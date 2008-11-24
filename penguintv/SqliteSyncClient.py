import time
import logging
import traceback
import tempfile
import sqlite3
import os

class SqliteSyncClient:
	def __init__(self):
		self._username = None
		self._password = None
		self._sync_file = None
		self._authenticated = False
		self._local_timestamp = 0
		self._no_updates = False
		self._readonly = False
		self._bad_db = False
		
	def set_username(self, username):
		if username == self._username:
			return
		self.finish()
		self._username = username
		
	def set_password(self, password):
		if password == self._password:
			return
		self.finish()
		self._password = password
		
	def set_readonly(self, readonly):
		self._readonly = readonly
		
	def finish(self, last_upload=[]):
		if self._sync_file is not None:
			db = self._get_db()
			if db is not None:
				self.submit_readstates(last_upload, do_upload=False, noclosedb=db)
				c = db.cursor()
				one_month = int(time.time()) - (60*60*24*30)
				c.execute('DELETE FROM readinfo WHERE timestamp < ?', (one_month,))
				db.commit()
				#c.execute('VACUUM')
				#db.commit()
				c.close()
				if len(last_upload) > 0:
					self._close_and_send_db(db)
				else:
					db.close()
				os.remove(self._sync_file)
			self._sync_file = None
			self._authenticated = False
		return True
	
	def authenticate(self):
		if len(self._username) == 0:
			return False
			
		if self._authenticated:
			self._authenticated = False
		
		try:
			success = self._do_authenticate()
		except Exception, e:
			logging.error("error authenticating: %s" % str(e))
			success = False
			
		self.__logging_in = False
		self._authenticated = success
		return success

	def submit_readstates(self, readstates, do_upload=True, noclosedb=None):
		"""Returns True on success, False on error"""
		
		if self._readonly:
			logging.debug("in readonly mode, not submitting")
			return True
			
		logging.debug("ArticleSync Submitting %i readstates" % len(readstates))
		if len(readstates) == 0:
			#logging.debug("(returning immediately)")
			return True
		
		if do_upload and noclosedb is not None:
			logging.error("Can't upload without closing DB, so this makes no sense")
		
		if noclosedb is None:
			db = self._get_db()
			if db is None:
				self._sync_file = None
				db = self._create_db()
		else:
			db = noclosedb
		
		try:
			c = db.cursor()
			c.execute(u'SELECT * FROM readinfo LIMIT 1')
		except Exception, e:
			logging.error("Bad Articlesync DB, recreating: %s" % str(e))
			self._sync_file = None
			db = self._create_db()
			c = db.cursor()
			
		timestamp = int(time.time())
			
		hashes = [r[0] for r in readstates]
		existing = []
		while len(hashes) > 0:
			subset = hashes[:900]
			qmarks = '?,'*(len(subset)-1)+'?'
			c.execute(u'SELECT hash FROM readinfo WHERE hash IN ('+qmarks+')', \
				tuple(subset))
			batch = c.fetchall()
			if batch is None: 
				batch = []
			existing = existing + batch
			hashes = hashes[900:]
		existing = [r[0] for r in existing]			
		
		for entry_hash, readstate in readstates:
			#logging.debug(": %s %i %i" % (entry_hash, timestamp, readstate))
			if entry_hash in existing:
				c.execute(u'UPDATE readinfo SET readstate=?, timestamp=? WHERE hash=?',
						(readstate, timestamp, entry_hash))
			else:
				c.execute(u'INSERT INTO readinfo (hash, timestamp, readstate) VALUES (?,?,?)',
					(entry_hash, timestamp, readstate))
					
		db.commit()
		c.close()
		
		if do_upload:
			return self._close_and_send_db(db)
		if noclosedb is None:
			db.close()
		return True
		
	def get_readstates(self, hashlist):
		"""takes a list of hashes, asks the db for their readstates
		   
		   returns a hash of entryhash:readstate"""
		  
		try: 
			db = self._get_db()
			c = db.cursor()
		except Exception, e:
			self._bad_db = True
			return None
			
		readstates = []
		while len(hashlist) > 0:
			subset = hashlist[:900]
			qmarks = '?,'*(len(subset)-1)+'?'
			try:
				c.execute(u'SELECT hash, readstate FROM readinfo WHERE hash IN ('+qmarks+')', \
					tuple(subset))
			except Exception, e:
				self._bad_db = True
				return None
			batch = c.fetchall()
			if batch is None: 
				batch = []
			readstates += batch
			hashlist = hashlist[900:]
			
		c.close()
		db.close()
		return readstates
	
	def get_readstates_since(self, timestamp):
		"""takes a timestamp, asks the db for hashes since then
		   
		   returns a hash of entryhash:readstate"""
		
		try:
			server_timestamp = self._get_server_timestamp()
		except Exception, e:
			logging.error("error getting timestamp: %s" % str(e))
			return []
		   
		if self._no_updates:
			#logging.debug("server time %i, our time %i" % (server_timestamp, self._local_timestamp))
			if server_timestamp == self._local_timestamp:
				#logging.debug("no updates last time, so no point checking")
				return []
				
		if server_timestamp < self._local_timestamp:
			logging.debug("server timestamp is less than local, so clocks must be off. Using their time")
			timestamp = server_timestamp
		
		
		try: 
			db = self._get_db(server_timestamp)
			c = db.cursor()
		except Exception, e:
			self._bad_db = True
			return None

		try:
			c.execute(u'SELECT hash, readstate FROM readinfo WHERE timestamp >= ?', (timestamp,))
		except Exception, e:
			self._bad_db = True
			return None
		new_hashes = c.fetchall()
		#logging.debug("result: %s" % str(new_hashes))
		c.execute(u'SELECT hash, readstate, timestamp FROM readinfo')
		r = c.fetchall()
		#for row in r:
		#	logging.debug("whole: %s" % str(row))
		c.close()
		db.close()
		if new_hashes is None:
			new_hashes = []
		if len(new_hashes) == 0:
			#logging.debug("No results, so if the server doesn't update next time we won't download it")
			self._no_updates = True
			return []
		return new_hashes
		
	def _get_db(self, server_timestamp=None):
		if self._bad_db:
			self._bad_db = False
			return self._create_db()
			
		if self._sync_file is None:
			return self._download_db()
			
		if server_timestamp is None:
			try:
				server_timestamp = self._get_server_timestamp()
			except Exception, e:
				logging.error("error getting timestamp: %s" % str(e))
				return None
			
		if server_timestamp != self._local_timestamp:
			#logging.debug("sync time unexpectedly changed %i %i" \
			#	% (server_timestamp, self._local_timestamp))
			return self._download_db()
		
		try:
			return sqlite3.connect(self._sync_file)
		except Exception, e:
			logging.error("error loading articlesync db: %s %s" % (type(e), str(e)))
			self._bad_db = True
			return None
		
	def _download_db(self):
		self._no_updates = False
		
		try:
			assert self._db_exists()
			#if not self._db_exists():
			#	return self._create_db()
		except Exception, e:
			logging.error("no db found: %s" % str(e))
			self._bad_db = True
			return None
			
		try:
			db_data = self._do_download_db()
		except Exception, e:
			logging.error("error downloading db: %s" % str(e))
			self._bad_db = True
			return None
			
		if self._sync_file is None:
			self._sync_file = tempfile.mkstemp(suffix='.db')[1]
		fp = open(self._sync_file, 'wb')
		fp.write(db_data)
		#logging.debug("Downloaded %i bytes" % fp.tell())
		fp.close()
		
		try:
			self._local_timestamp = self._get_server_timestamp()
		except Exception, e:
			logging.error("error getting timestamp: %s" % str(e))
		
		try:
			return sqlite3.connect(self._sync_file)
		except Exception, e:
			#problem with the db, have to start over
			logging.error("error loading articlesync db (2): %s %s" % (type(e), str(e)))
			self._bad_db = True
			return None
		
	def _create_db(self):
		logging.debug("creating new db")
		self._sync_file = tempfile.mkstemp(suffix='.db')[1]
		db = sqlite3.connect(self._sync_file)
		c = db.cursor()
		c.execute(u"""CREATE TABLE readinfo 
			(
				id INTEGER PRIMARY KEY,
				hash TEXT NOT NULL,
				timestamp INTEGER NOT NULL,
				readstate BOOL NOT NULL
			);""")
			
		db.commit()
		c.close()
		self._local_timestamp = int(time.time())
		#logging.debug("SETTING server TIMESTAMP2: %i" % self._local_timestamp)
		try:
			if not self._set_server_timestamp(self._local_timestamp):
				logging.error("error setting timestamp")
		except Exception, e:
			logging.error("error setting timestamp: %s" % str(e))
		return db
		
	def _close_and_send_db(self, db):
		"""close the db and send it"""
		db.close()
		fp = open(self._sync_file, 'rb')
		try:
			success = self._upload_db(fp)
		except Exception, e:
			logging.error("error uploading db: %s" % str(e))
			success = False
		if not success:
			logging.debug("error uploading readstate database")
			return False
		#logging.debug("Uploaded %i bytes" % fp.tell())
		fp.close()
		self._local_timestamp = int(time.time())
		#logging.debug("SETTING server TIMESTAMP3: %i" % self._local_timestamp)
		try:
			if not self._set_server_timestamp(self._local_timestamp):
				logging.error("error setting timestamp")
				return False
		except Exception, e:
			logging.error("error setting timestamp: %s" % str(e))
			return False
		return True
		
	def _reset_db(self):
		db = self._create_db()
		self._close_and_send_db(db)
		
##### extended class functions#####

	def _do_authenticate(self):
		"""Authenticates to the server with self._username and self._password.
		Returns True on success and False on failure"""
		logging.error("must be implemented in subclass")
		assert False
					
	def _set_server_timestamp(self, timestamp):
		logging.error("must be implemented in subclass")
		assert False
		
	def _get_server_timestamp(self):
		logging.error("must be implemented in subclass")
		assert False

	def _db_exists(self):
		logging.error("must be implemented in subclass")
		assert False
		
	def _do_download_db(self):
		logging.error("must be implemented in subclass")
		assert False

	def _upload_db(self, fp):
		logging.error("must be implemented in subclass")
		assert False

