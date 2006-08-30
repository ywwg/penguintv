# Written by Owen Williams
# see LICENSE for license information
#
# portions ported from totem/src/bacon_message_connection.c
from utils import GlobDirectoryWalker
import random
import os,pwd,stat,time
from socket import *
from SocketServer import *

import gobject

prefix='penguintv'

class PTVAppSocket:
	def __init__(self, callback):
		self.socket = socket(AF_UNIX,SOCK_DGRAM)
		self.is_server = True
		self.socket_file = get_socket_filename()
		self.callback = callback
		try:
			self.socket.bind(self.socket_file)
			#self.socket.listen(5)
			self.socket.setblocking(0)
			gobject.io_add_watch(self.socket, gobject.IO_IN, self.server_cb)
		except error, e:
			try:
				self.socket.connect(self.socket_file)
				self.is_server = False
			except error, e:
				os.remove(self.socket_file)
				self.__init__(callback)
				
	def server_cb(self, source, condition):
		if not self.is_server:
			print "I'm not a server"
			return False
		
		#self.socket.accept()
		data = self.socket.recv(4096)
		self.callback(data)
		return True
		
	def send(self, data):
		if self.is_server:
			print "I am not a client"
			return
		self.socket.send(data)
				
	def close(self):
		self.socket.close()
		if self.is_server:
			try:
				os.remove(self.socket_file)
			except Exception, e:
				print "error removing socket file",e
		
def is_owned_by_user_and_socket(path):
	try:
		s = os.stat(path)
		#st_mode, st_ino, st_dev, st_nlink, st_uid, st_gid, st_size, st_atime, st_mtime, st_ctime
		if s[4] != os.geteuid():
			return False
		if stat.S_ISSOCK(s[0]) == 0:
			return False
	except:
		return False
	return True

def get_tmp_dir():
	#based off API description of glib's g_get_tmp_dir
	if os.environ.has_key('TMPDIR'):
		return os.environ['TMPDIR']
	if os.environ.has_key('TMP'):
		return os.environ['TMP']
	if os.environ.has_key('TEMP'):
		return os.environ['TEMP']
	return "/tmp"
				
def find_file_with_pattern(dir, pattern):
	for file in GlobDirectoryWalker(dir, pattern):
		if is_owned_by_user_and_socket(file):
			return file
	return None
				
def get_socket_filename():
	pattern = prefix+"."+pwd.getpwuid(os.getuid())[0]+".*"
	tmpdir = get_tmp_dir()
	filename = find_file_with_pattern (tmpdir, pattern)
	if filename is None:
		newfile = prefix+"."+pwd.getpwuid(os.getuid())[0]+"."+str(random.randint(1,1000000))
		path = tmpdir+"/"+newfile
	else:
		path = filename
	return path
	
	
