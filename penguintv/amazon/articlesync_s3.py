import time
import logging
import traceback
import tempfile
import sqlite3
import os

import S3

#BUCKET_NAME will be prepended with access key
BUCKET_NAME_SUF = '-penguintv-article-sync-db'
KEYNAME = 'penguintv-syncdb-1'
REF_KEYNAME = 'penguintv-syncdb-ref'

class SyncClient:
	def __init__(self, username, password):
		self._access_key = username
		self._secret_key = password
		self._conn = None
		self._bucket = self._access_key.lower() + BUCKET_NAME_SUF
		self._sync_file = None
		self._authenticated = False
		self._old_refcount = 0
		
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
		logging.debug("SHUTTING DOWN S3")
		if self._sync_file is not None:
			db = self._get_db()
			if db is not None:
				if len(last_upload) > 0:
					logging.debug("BUT UPLOADING TOO")
					self.submit_readstates(last_upload, do_upload=False, noclosedb=db)
				else:
					logging.debug("nothing to upload")
				c = db.cursor()
				c.execute('VACUUM')
				db.commit()
				self._close_and_send_db(db)
				os.remove(self._sync_file)
			self._sync_file = None
			self._unref()
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
					logging.debug("true, we created the bucket")
					return True
				else:
					self.__logging_in = False
					return False
			else:
				self._authenticated = True
				self.__logging_in = False
				logging.debug("true, the bucket exists")
				return True
		
		response = \
			   self._conn.create_located_bucket(self._bucket, S3.Location.DEFAULT)
		self.__logging_in = False
		if response.http_response.status == 200:
			self._authenticated = True
			self.__logging_in = False
			logging.debug("true, we created the bucket2")
			return True
		else:
			self.__logging_in = False
			return False
			
	def _ref(self):
		old_val, active_syncs = self._get_refcount()
		active_syncs += 1
		logging.debug("current ref is now %i" % active_syncs)
		resp = self._conn.put(self._bucket, REF_KEYNAME, str(active_syncs))
		if resp.http_response.status != 200:
			logging.error("error incrementing ref")
		return old_val, active_syncs
			
	def _unref(self):
		old_val, active_syncs = self._get_refcount()
		active_syncs -= 1
		logging.debug("after unref, current ref is now %i" % active_syncs)
		if active_syncs < 0:
			logging.warning("less than zero active syncs?")
			active_syncs = 0
		resp = self._conn.put(self._bucket, REF_KEYNAME, str(active_syncs))
		if resp.http_response.status != 200:
			logging.error("error decrementing ref")
		return old_val, active_syncs
		
	def _get_refcount(self):
		assert self._authenticated
		resp = self._conn.get(self._bucket, REF_KEYNAME)
		if resp.http_response.status == 404:
			self._conn.put(self._bucket, REF_KEYNAME, "0")
			return 0,0
		elif resp.http_response.status != 200:
			logging.error("couldn't get current ref: %s %s" % resp.message)
			return 0,0
		old_val = self._old_refcount
		self._old_refcount = int(resp.object.data)
		return old_val, int(resp.object.data)
		
	def submit_readstates(self, readstates, do_upload=True, noclosedb=None):
		"""takes a list of entryhash, readstate and submits it to S3 as:
			KEYNAME=timestamp-entryid
			VALUE=readstate.
			
			Returns True on success, False on error"""
			
		assert self._conn is not None
		if do_upload and noclosedb is not None:
			logging.error("Can't upload without closing DB, so this makes no sense")
		
		if noclosedb is None:
			db = self._get_db()
			if db is None:
				return False
		else:
			db = noclosedb
		
		if len(readstates) > 0:
			timestamp = int(time.time())
			
			c = db.cursor()
			qmarks = '?,'*(len(readstates)-1)+'?'
			hashes = [r[0] for r in readstates]
			c.execute(u'SELECT hash FROM readinfo WHERE hash IN ('+qmarks+')', \
					tuple(hashes))
			existing = c.fetchall()
			if existing is None: existing = []
			else: existing = [r[0] for r in existing]
			
			for entry_hash, readstate in readstates:
				logging.debug("writing: %s %i %i" % (entry_hash, timestamp, readstate))
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
		logging.debug("Not uploading right now")
		return True
	
	def get_readstates_since(self, timestamp):
		"""takes a timestamp, asks the bucket for all the keys.  parse
		   keys for timestamp, use that to know what to ask for
		   
		   returns a hash of entryhash:readstate"""
		   
		assert self._conn is not None
		
		db = self._get_db()
		if db is None:
			return []
			
		c = db.cursor()
		logging.debug("getting updated entries since %i" % timestamp)
		c.execute(u'SELECT hash, readstate FROM readinfo WHERE timestamp >= ?', (timestamp,))
		new_hashes = c.fetchall()
		logging.debug("result: %s" % str(new_hashes))
		c.execute(u'SELECT hash, readstate, timestamp FROM readinfo')
		r = c.fetchall()
		for row in r:
			logging.debug("whole: %s" % str(row))
		c.close()
		db.close()
		if new_hashes is None:
			return []
		return new_hashes
		
	def _get_db(self):
		old_val, active_syncs = self._get_refcount()
		if old_val > 1 or active_syncs > 1:
			logging.debug("more than one instance running, so download db")
			return self._download_db()
		
		if self._sync_file is None:
			return self._download_db()
		else:
			return sqlite3.connect(self._sync_file)
		
	def _download_db(self):
		response = self._conn.get(self._bucket, KEYNAME)
		if response.http_response.status == 404:
			return self._create_db()
		elif response.http_response.status != 200:
			return None
		
		db_data = response.object.data
		if self._sync_file is None:
			self._ref()
			self._sync_file = tempfile.mkstemp(suffix='.db')[1]
		fp = open(self._sync_file, 'wb')
		fp.write(db_data)
		logging.debug("Downloaded %i bytes" % fp.tell())
		fp.close()
		return sqlite3.connect(self._sync_file)
		
	def _create_db(self):
		self._ref()
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
		return db
		
	def _close_and_send_db(self, db):
		"""close the db and send it"""
		db.close()
		fp = open(self._sync_file, 'rb')
		response = self._conn.put(self._bucket, KEYNAME, fp.read())
		logging.debug("Uploaded %i bytes" % fp.tell())
		fp.close()
		if response.http_response.status != 200:
			return False
		return True
		
	def _reset_db(self):
		db = self._create_db()
		self._close_and_send_db(db)

