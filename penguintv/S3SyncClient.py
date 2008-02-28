import logging
import threading

import gettext
_=gettext.gettext

from SqliteSyncClient import SqliteSyncClient
from amazon import S3

#BUCKET_NAME will be prepended with access key
BUCKET_NAME_SUF = '-penguintv-article-sync-db'
KEYNAME = 'penguintv-syncdb-1'
STAMP_KEYNAME = 'penguintv-syncdb-timestamp'

class S3SyncClient(SqliteSyncClient):
	def __init__(self):
		SqliteSyncClient.__init__(self)
		self.__transfer_lock = threading.Lock()
		
		self._username = ""
		self._bucket = self._username.lower() + BUCKET_NAME_SUF
		self._conn = None
		
	def get_parameters(self):
		return [
			(_("Access Key"), "username", "", False),
			(_("Secret Key"), "password", "", True)
			]
		
	def set_username(self, username):
		SqliteSyncClient.set_username(self, username)
		self._bucket = self._username.lower() + BUCKET_NAME_SUF

	def _do_authenticate(self):
		self._conn = S3.AWSAuthConnection(self._username, self._password)
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
					return True
				else:
					return False
			else:
				return True
		
		response = \
			   self._conn.create_located_bucket(self._bucket, S3.Location.DEFAULT)
		if response.http_response.status == 200:
			return True
		else:
			return False
			
	def _set_server_timestamp(self, timestamp):
		assert self._authenticated
		logging.debug("TIMESTAMPING SUBMISSION: %i" % timestamp)
		resp = self._conn.put(self._bucket, STAMP_KEYNAME, str(timestamp))
		if resp.http_response.status != 200:
			logging.error("error submitting timestamp")
			return False
		return True
		
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

	def _db_exists(self):
		response = self._conn.list_bucket(self._bucket)
		if response.http_response.status != 200:
			return False
		
		for entry in response.entries:
			if entry.key == KEYNAME:
				return True
		return False
		
	def _do_download_db(self):
		self.__transfer_lock.acquire()
		response = self._conn.get(self._bucket, KEYNAME)
		self.__transfer_lock.release()
		if response.http_response.status != 200:
			return None
		return response.object.data

	def _upload_db(self, fp):
		self.__transfer_lock.acquire()
		response = self._conn.put(self._bucket, KEYNAME, fp.read())
		self.__transfer_lock.release()
		return response.http_response.status == 200
