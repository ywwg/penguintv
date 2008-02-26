import time
import logging
import traceback
import tempfile
import sqlite3
import os
import threading

import S3

#BUCKET_NAME will be prepended with access key
BUCKET_NAME_SUF = '-penguintv-article-sync-db'
KEYNAME = 'penguintv-syncdb-1'
STAMP_KEYNAME = 'penguintv-syncdb-timestamp'

class SyncClient:
	def __init__(self, username, password):
		self._access_key = username
		self._secret_key = password
		self._conn = None
		self._bucket = self._access_key.lower() + BUCKET_NAME_SUF
		self._sync_file = None
		self._authenticated = False
		self._local_timestamp = 0
		self._no_updates = False
		self.__transfer_lock = threading.Lock()
		
	def set_username(self, username):
		if username == self._access_key:
			return
		self.finish()
		self._access_key = username
		self._bucket = self._access_key.lower() + BUCKET_NAME_SUF
		
	def set_password(self, password):
		if password == self._secret_key:
			return
		self.finish()
		self._secret_key = password
		
	def finish(self, last_upload=[]):
		logging.debug("TIDYING UP S3")
		if self._sync_file is not None:
			db = self._get_db()
			if db is not None:
				self.submit_readstates(last_upload, do_upload=False, noclosedb=db)
				c = db.cursor()
				one_month = int(time.time()) - (60*60*24*30)
				c.execute('DELETE FROM readinfo WHERE timestamp < ?', (one_month,))
				db.commit()
				c.execute('VACUUM')
				db.commit()
				c.close()
				if len(last_upload) > 0:
					self._close_and_send_db(db)
				else:
					db.close()
				os.remove(self._sync_file)
			self._sync_file = None
			self._authenticated = False
			self._conn = None
		else:
			logging.debug("no sync file, so nothing accomplished anyway")
		return True
	
	def authenticate(self):
		if len(self._access_key) == 0:
			return False
			
		if self._authenticated:
			self._authenticated = False
		
		self._conn = S3.AWSAuthConnection(self._access_key, self._secret_key)
		#the only way to "authenticate" is to list buckets.  if list is
		#empty, try creating the bucket.  success?  it worked!  failure? 
		#bad keys
		
		buckets = [x.name for x in self._conn.list_all_my_buckets().entries]
		if len(buckets) > 0:
			if self._bucket not in buckets:
				#try creating our bucket
				response = \
				   self._conn.create_located_bucket(self._bucket, S3.Location.DEFAULT)
				if response.http_response.status == 200:
					self._authenticated = True
					self.__logging_in = False
					return True
				else:
					self.__logging_in = False
					return False
			else:
				self._authenticated = True
				self.__logging_in = False
				return True
		
		response = \
			   self._conn.create_located_bucket(self._bucket, S3.Location.DEFAULT)
		self.__logging_in = False
		if response.http_response.status == 200:
			self._authenticated = True
			self.__logging_in = False
			return True
		else:
			self.__logging_in = False
			return False
	
	def _set_server_timestamp(self):
		assert self._authenticated
		timestamp = int(time.time())
		logging.debug("TIMESTAMPING SUBMISSION: %i" % timestamp)
		resp = self._conn.put(self._bucket, STAMP_KEYNAME, str(timestamp))
		if resp.http_response.status != 200:
			logging.error("error submitting timestamp")
			return 0
		return timestamp
		
	def _get_server_timestamp(self):
		assert self._authenticated
		self.__transfer_lock.acquire()
		resp = self._conn.get(self._bucket, STAMP_KEYNAME)
		if resp.http_response.status == 404:
			self._conn.put(self._bucket, STAMP_KEYNAME, "0")
			self.__transfer_lock.release()
			return 0
		elif resp.http_response.status != 200:
			logging.error("couldn't get last submit time: %s" % resp.message)
			self.__transfer_lock.release()
			return 0
		self.__transfer_lock.release()
		
		return int(resp.object.data)
	
	def submit_readstates(self, readstates, do_upload=True, noclosedb=None):
		"""takes a list of entryhash, readstate and submits it to S3 as:
			KEYNAME=timestamp-entryid
			VALUE=readstate.
			
			Returns True on success, False on error"""
			
		assert self._conn is not None
		
		logging.debug("ArticleSync Submitting %i readstates" % len(readstates))
		if len(readstates) == 0:
			logging.debug("(returning immediately)")
			return True
		
		if do_upload and noclosedb is not None:
			logging.error("Can't upload without closing DB, so this makes no sense")
		
		if noclosedb is None:
			db = self._get_db()
			if db is None:
				return False
		else:
			db = noclosedb
		
		timestamp = int(time.time())
		c = db.cursor()
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
		logging.debug("Not uploading just yet")
		return True
	
	def get_readstates_since(self, timestamp):
		"""takes a timestamp, asks the bucket for all the keys.  parse
		   keys for timestamp, use that to know what to ask for
		   
		   returns a hash of entryhash:readstate"""
		   
		assert self._conn is not None
		
		if self._no_updates:
			server_timestamp = self._get_server_timestamp()
			logging.debug("server time %i, our time %i" % (server_timestamp, self._local_timestamp))
			if server_timestamp == self._local_timestamp:
				logging.debug("no updates last time, so no point checking")
				return []
		
		db = self._get_db()
		if db is None:
			return []
			
		c = db.cursor()
		c.execute(u'SELECT hash, readstate FROM readinfo WHERE timestamp >= ?', (timestamp,))
		new_hashes = c.fetchall()
		#logging.debug("result: %s" % str(new_hashes))
		c.execute(u'SELECT hash, readstate, timestamp FROM readinfo')
		r = c.fetchall()
		#for row in r:
		#	logging.debug("whole: %s" % str(row))
		c.close()
		db.close()
		if new_hashes is None:
			logging.debug("No results, so if the server doesn't update next time we won't download it")
			self._no_updates = True
			return []
		return new_hashes
		
	def _get_db(self):
		if self._sync_file is None:
			return self._download_db()
			
		server_timestamp = self._get_server_timestamp()
		if server_timestamp != self._local_timestamp:
			logging.debug("sync time unexpectedly changed %i %i" \
				% (server_timestamp, self._local_timestamp))
			return self._download_db()
		
		return sqlite3.connect(self._sync_file)
		
	def _download_db(self):
		self._no_updates = False
		self.__transfer_lock.acquire()
		response = self._conn.get(self._bucket, KEYNAME)
		self.__transfer_lock.release()
		if response.http_response.status == 404:
			return self._create_db()
		elif response.http_response.status != 200:
			return None
		
		db_data = response.object.data
		if self._sync_file is None:
			self._sync_file = tempfile.mkstemp(suffix='.db')[1]
		fp = open(self._sync_file, 'wb')
		fp.write(db_data)
		logging.debug("Downloaded %i bytes" % fp.tell())
		fp.close()
		
		self._local_timestamp = self._get_server_timestamp()
		
		return sqlite3.connect(self._sync_file)
		
	def _create_db(self):
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
		self._local_timestamp = self._set_server_timestamp()
		logging.debug("SETTING S3 TIMESTAMP2: %i" % self._local_timestamp)
		return db
		
	def _close_and_send_db(self, db):
		"""close the db and send it"""
		db.close()
		fp = open(self._sync_file, 'rb')
		self.__transfer_lock.acquire()
		response = self._conn.put(self._bucket, KEYNAME, fp.read())
		self.__transfer_lock.release()
		logging.debug("Uploaded %i bytes" % fp.tell())
		fp.close()
		if response.http_response.status != 200:
			return False
			
		self._local_timestamp = self._set_server_timestamp()
		logging.debug("SETTING S3 TIMESTAMP3: %i" % self._local_timestamp)
		return True
		
	def _reset_db(self):
		db = self._create_db()
		self._close_and_send_db(db)

