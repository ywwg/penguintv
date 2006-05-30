# Written by Owen Williams
# see LICENSE for license information

import ptvDB
import pycurl
from types import *
import ThreadPool
import time
import os,os.path
import glob
import BTDownloader
import HTTPDownloader
from utils import format_size

import utils

import gnome
import gnomevfs

FINISHED=0
FINISHED_AND_PLAY=1
STOPPED=2
FAILURE=-1


#Downloader API:
#constructor takes:  media, params, resume, queue, progress_callback, finished_callback
#  media:  the media dic
#  params: optional params, like for btdownloader
#  resume: are we supposed to resume?
#  queue:  are we supposed queue for playback when download is finished?  this variable is just passed around
#  progress_callback:  function to call for progress update.
#          arg of this is: (media, progress as 0 < x < 1, and text formatted message of progress)
#          the callback will return 1 if we should cancel download
#  finished_callback:  function to call when finished.
#          args is: (media, status, message)
#              where status is the enum above

class MediaManager:
	def __init__(self, progress_callback=None, finished_callback=None):
		self.index=0
		self.pool = ThreadPool.ThreadPool(5,"MediaManager")
		self.db = ptvDB.ptvDB()
		self.time_appendix=0
		self.bt_settings = {'min_port':6881, 'max_port':6999, 'ul_limit':0}
		self.id_time=0
		self.quitting = False
		if finished_callback:
			self.pool_finished_callback = finished_callback
		else:
			self.pool_finished_callback = self._basic_finished_callback
			
		if progress_callback:
			self.pool_progress_callback = progress_callback
		else:
			self.pool_progress_callback = self._basic_progress_callback	
		try:
			home=os.getenv('HOME')
			os.stat(home+'/.penguintv/media')
		except:
			try:
				os.mkdir(home+'/.penguintv/media')
			except:
				raise NoDir, "error creating " +home+'/.penguintv/media'
		self.media_dir = home+'/.penguintv/media'
	
	def finish(self):
		self.quitting = True
		self.pool.joinAll()
		del self.pool
		
	def __del__(self):
		self.finish()
		
	def set_bt_settings(self, bt_settings):
		self.bt_settings = bt_settings
		
	def get_id(self):
		cur_time = int(time.time())
		
		if self.id_time == cur_time:
			self.time_appendix = self.time_appendix+1
		else:
			self.id_time = cur_time
			self.time_appendix=0
		
		return str(self.id_time)+"+"+str(self.time_appendix)
		
	def show_downloads(self):
		gnome.url_show("file://"+self.media_dir+"/"+utils.get_dated_dir())
		
	def download_entry(self, entry_id, queue=False, resume=False):
		"""queues a download
		 will interact with bittorrent python
	   use btlaunchmany code to write our own downloader
		 just need to change init funcs, hijack status funcs, add cancelling"""
		media_list = self.db.get_entry_media(entry_id)
		files=""
		if len(media_list)==0:
			return
		for media in media_list:
			self.download(media['media_id'], queue, resume)
			
	def download(self, media_id, queue=False, resume=False):
		"""queues a download"""
		media = self.db.get_media(media_id)
		media['downloader_index']=self.index
		media['download_status']=1			
		if media['file'] is None:
			filename = os.path.basename(media['url'])
			filen, ext = os.path.splitext(filename)
			ext = ext.split('?')[0] #grrr lugradio...
			media['file']=self.media_dir+"/"+utils.get_dated_dir()+"/"+filen+ext
			dated_dir = os.path.split(os.path.split(media['file'])[0])[1]
			try: #make sure
				os.stat(self.media_dir+"/"+dated_dir)
			except:
				os.mkdir(self.media_dir+"/"+dated_dir)
			if self.db.media_exists(media['file']): #if the filename is in the db, rename
				media['file']=self.media_dir+"/"+utils.get_dated_dir()+"/"+filen+"-"+self.get_id()+ext
			else:
				try:
					os.stat(media['file'])  #if this raises exception, the file doesn't exist and we're ok
					media['file']=self.media_dir+"/"+utils.get_dated_dir()+"/"+filen+"-"+self.get_id()+ext #if not, get new name
				except:
					pass #we're ok
			
			if resume==False:
				self.db.delete_media(media_id)
			#else:
			#	print "resuming using existing filename: "+str(media['file'])
		extension = os.path.splitext(media['url'])[1]
		
		if media['mimetype'] == 'application/x-bittorrent' or extension.upper()==".TORRENT":
			params = [
				'--minport', str(self.bt_settings['min_port']),
				'--maxport', str(self.bt_settings['max_port']),
				'--max_upload_rate', str(self.bt_settings['ul_limit'])]
				
			downloader = BTDownloader.BTDownloader(media, self.media_dir, params,True, queue, self.pool_progress_callback,self.pool_finished_callback)
			print "queueing "+str(media)
			self.pool.queueTask(downloader.download)
			pass
		else: #http regular download
			downloader = HTTPDownloader.HTTPDownloader(media, self.media_dir, None, resume, queue, self.pool_progress_callback, self.pool_finished_callback)
			print "queueing "+str(media)
			self.pool.queueTask(downloader.download)
			
		self.db.set_media_download_status(media['media_id'],1)
		#self.db.set_media_viewed(media['media_id'],False)
		self.db.set_media_filename(media['media_id'],media['file'])
		self.index=self.index+1
		
	def bt_progress_callback(self, data):
		if self.quitting == True:
			return 1
		self.pool_progress_callback(data)
		
	def _basic_finished_callback(self, data):
		#filename = data[0]['file']
		#info = data[1:]
		#print filename+" "+str(info)
		print data
		self.db.set_media_download_status(data[0]['media_id'],ptvDB.D_DOWNLOADED)	
			
	def _basic_progress_callback(self, data):
		#media, blocks, blocksize, totalsize=data
		#percent = (blocks*blocksize*100) / totalsize
		#if percent>100:
	#		percent = 100
		#if percent%10 == 0:
		#	print media['file']+" "+str(percent)+"%"
		print os.path.split(data[0]['file'])[1]+" "+data[2]
			
	def get_download_count(self):
		try:
			return self.pool.getTaskCount()
		except:
			return 0
		
	def pause_all_downloads(self):
		print "downloads paused"
		self.pool.joinAll(False,True) #don't wait for tasks, but let the threads die naturally
		self.pool.setThreadCount(5)
			
	def get_disk_usage(self):
		size = 0
		try:
			#filelist = glob.glob(self.media_dir+"/*")
			for f in utils.GlobDirectoryWalker(self.media_dir+"/"):
				size = size+os.stat(f)[6]
		except:
			pass
		return size
		
	def generate_playlist(self):
		dated_dir = utils.get_dated_dir()
		try:
			os.stat(self.media_dir+"/"+dated_dir)
		except:
			os.mkdir(self.media_dir+"/"+dated_dir)
		f = open(self.media_dir+"/"+dated_dir+"/playlist.m3u",'w')
		f.write('#EXTM3U\n')
		
		for item in glob.glob(self.media_dir+"/"+dated_dir+"/*"):
			filename = os.path.split(item)[1]
			if filename != "playlist.m3u":
				f.write(filename+"\n")
		f.close()
		
	def update_playlist(self, media):
		"""Adds media to the playlist in its directory"""
		
		try:
			os.stat(media['file'])
		except:
			return
			
		dated_dir = os.path.split(os.path.split(media['file'])[0])[1]
			
		try:
			os.stat(self.media_dir+"/"+dated_dir+"/playlist.m3u")
			f = open(self.media_dir+"/"+dated_dir+"/playlist.m3u",'a')
		except:
			f = open(self.media_dir+"/"+dated_dir+"/playlist.m3u",'w')
			f.write('#EXTM3U\n')
		
		f.write(os.path.split(media['file'])[1]+"\n")
		f.close()

class NoDir(Exception):
	def __init__(self,durr):
		self.durr = durr
	def __str__(self):
		return "no such directory: "+self.durr
