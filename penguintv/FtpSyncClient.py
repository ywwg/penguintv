import logging
import threading
import ftplib
import socket
import time
import tempfile

from SqliteSyncClient import SqliteSyncClient

FILENAME = 'penguintv-syncdb-1.db'
STAMP_FILENAME = 'penguintv-syncdb-timestamp'

class FtpSyncClient(SqliteSyncClient):
	def __init__(self):
		#username = 'transfer'
		#password = 'upwego'
		#hostname = 'ftp.powderhouse.net'
		#path = '/test'
		#port = 21
		SqliteSyncClient.__init__(self)
		self.__transfer_lock = threading.Lock()
		
		self._username = ""
		self._password = ""
		self._hostname = ""
		self._port = 21
		self._path = "/"
		self._ftp = None
		self._stampfile = tempfile.mkstemp(suffix='.txt')[1]
		self._last_conn_check = 0
		
	def get_parameters(self):
		return [
			(_("FTP Server"), "hostname", "", False),
			(_("Port"), "port", "21", False),
			(_("Username"), "username", "", False),
			(_("Password"), "password", "", True),
			(_("Path"), "path", "/", False)
			]
			
	def set_hostname(self, hostname):
		if hostname == self._hostname:
			return
		self.finish()
		self._hostname = hostname
		
	def set_port(self, port):
		try:
			port = int(port)
			self._port = -1
		except:
			return False
		if port == self._port:
			return
		self.finish()
		self._port = port
		
	def set_path(self, path):
		if path == self._path:
			return
		self.finish()
		self._path = path
			
	def _do_authenticate(self, tryreconnect=False):
		if self._ftp is not None and not tryreconnect:
			self._ftp.quit()
			self._ftp = None
		else:
			self._ftp = ftplib.FTP()
		
		try:
			self._ftp.connect(self._hostname, self._port)
		except:
			return False
			
		try:
			self._ftp.login(self._username, self._password)
		except:
			return False
			
		try:
			self._ftp.cwd(self._path)
		except:
			return False
			
		self._last_conn_check = int(time.time())
		return True
			
	def _set_server_timestamp(self, timestamp):
		assert self._authenticated
		if not self._check_connection():
			return False
		self.__transfer_lock.acquire()
		f = open(self._stampfile, 'w')
		f.write(str(timestamp))
		f.close()
		try:
			f = open(self._stampfile, 'r')
			self._ftp.storlines('STOR %s' % STAMP_FILENAME, f)
			f.close()
			self.__transfer_lock.release()
			return True
		except:
			self.__transfer_lock.release()
			return False
		
	def _get_server_timestamp(self):
		timestamp = None
		def retr_cb(line):
			timestamp = int(line)
		
		assert self._authenticated
		if not self._check_connection():
			return -1
			
		self.__transfer_lock.acquire()
		self._ftp.retrlines('RETR %s' % STAMP_FILENAME, retr_cb)
		for i in range(0,10):
			if timestamp is not None:
				self.__transfer_lock.release()
				return timestamp
			time.sleep(1)
		self.__transfer_lock.release()
		return -1
		
	def _db_exists(self):
		stamp_exists = False
		def dir_cb(line):
			if STAMP_FILENAME in line:
				stamp_exists = True
		
		if not self._check_connection():
			return False
				
		self.__transfer_lock.acquire()
		self._ftp.dir(dir_cb)
		for i in range(0,10):
			if stamp_exists:
				self.__transfer_lock.release()
				return True
		self.__transfer_lock.release()
		return False
		
	def _do_download_db(self):
		if not self._check_connection():
			return None
			
		self.__transfer_lock.acquire()
		filesize = self._ftp.size(FILENAME)
		if filesize is None:
			return None
		
		data = ""
		def retr_cb(line):
			data += line
			
		wait = 0
		last_size = 0
		while len(data) < filesize and wait < 30:
			if len(data) > last_size:
				wait = 0
				last_size = len(data)
			time.sleep(1)
			wait += 1
		self.__transfer_lock.release()
		if len(data) < filesize:
			return None
		return data

	def _upload_db(self, fp):
		if not self._check_connection():
			return False
		self.__transfer_lock.acquire()
		try:
			self._ftp.storbinary('STOR %s' % FILENAME, fp)
		except:
			self.__transfer_lock.release()
			return False
		self.__transfer_lock.release()
		return True
		
	def _check_connection(self):
		def dir_cb(line):
			pass
		
		if int(time.time()) - self._last_conn_check < 30:
			logging.debug("last connection was recent, assuming ok")
			return True
			
		#logging.debug("checking connection")
		try:
			self._ftp.dir(dir_cb)
			#logging.debug("connection still up")
			return True
		except Exception, e:
			#logging.debug("exception checking connection: %s" % str(e))
			if not self._do_authenticate(tryreconnect=True):
				logging.debug("can't reconnect")
				return False
			logging.debug("reconnected")
			return True
