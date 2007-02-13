# Written by Owen Williams
# see LICENSE for license information

import ptvDB
import pycurl
from types import *
import ThreadPool
import time
import os,os.path
import glob
import copy

import Downloader
#import BTDownloader  loaded when needed
#import HTTPDownloader  loaded when needed

from utils import format_size

import utils

try:
	import gnome
	HAS_GNOME = True
except:
	HAS_GNOME = False

from penguintv import DOWNLOAD_ERROR, DOWNLOAD_PROGRESS, DOWNLOAD_WARNING, DOWNLOAD_QUEUED
from Downloader import QUEUED, DOWNLOADING, FINISHED, FINISHED_AND_PLAY, STOPPED, FAILURE, PAUSED

RUNNING = 0
PAUSING = 1 
PAUSED  = 2

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
		self.downloads = []
		self.db = ptvDB.ptvDB()
		self.time_appendix=0
		self.bt_settings = {'min_port':6881, 'max_port':6999, 'ul_limit':0}
		self.id_time=0
		self.quitting = False
		self.pause_state = RUNNING
		if finished_callback:
			self.app_callback_finished = finished_callback
		else:
			self.app_callback_finished = self._basic_finished_callback
			
		if progress_callback:
			self.app_callback_progress = progress_callback
		else:
			self.app_callback_progress = self._basic_progress_callback	
		home=self.db.home
		try:	
			os.stat(os.path.join(home,'media'))
		except:
			try:
				os.mkdir(os.path.join(home, 'media'))
			except:
				raise NoDir, "error creating " +home+'/media'
		self.media_dir = os.path.join(home, 'media')
	
	def finish(self):
		self.quitting = True
		try:
			self.pool.joinAll()
			del self.pool
		except:
			pass
		
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
		if HAS_GNOME:
			gnome.url_show("file://"+self.media_dir+"/"+utils.get_dated_dir())
		
	def download_entry(self, entry_id, queue=False, resume=False):
		"""queues a download
		 will interact with bittorrent python
	   use btlaunchmany code to write our own downloader
		 just need to change init funcs, hijack status funcs, add cancelling"""
		media_list = self.db.get_entry_media(entry_id)
		if len(media_list)==0:
			return
		for media in media_list:
			self.download(media['media_id'], queue, resume)
			
	def download(self, media_id, queue=False, resume=False):
		"""queues a download"""
		for downloader in self.downloads:
			if downloader.media['media_id'] == media_id:
				self.downloads.remove(downloader)
				break
		
		media = self.db.get_media(media_id)
		media['downloader_index']=self.index
		media['download_status']=1
		media.setdefault('size',0)			
		if media['file'] is None:
			filename = os.path.basename(media['url'])
			filen, ext = os.path.splitext(filename)
			ext = ext.split('?')[0] #grrr lugradio...
			media['file']=os.path.join(self.media_dir, utils.get_dated_dir(), filen+ext)
			dated_dir = os.path.split(os.path.split(media['file'])[0])[1]
			try: #make sure
				os.stat(os.path.join(self.media_dir, dated_dir))
			except:
				os.mkdir(os.path.join(self.media_dir, dated_dir))
			if self.db.media_exists(media['file']): #if the filename is in the db, rename
				media['file']=os.path.join(self.media_dir, utils.get_dated_dir(), filen+"-"+self.get_id()+ext)
			else:
				try:
					os.stat(media['file'])  #if this raises exception, the file doesn't exist and we're ok
					media['file']=os.path.join(self.media_dir, utils.get_dated_dir(), filen+"-"+self.get_id()+ext) #if not, get new name
				except:
					pass #we're ok
			
			if not resume:
				self.db.delete_media(media_id)
			#else:
			#	print "resuming using existing filename: "+str(media['file'])
		extension = os.path.splitext(media['url'])[1]
		
		if media['mimetype'] == 'application/x-bittorrent' or extension.upper()==".TORRENT":
			params = [
				'--minport', str(self.bt_settings['min_port']),
				'--maxport', str(self.bt_settings['max_port']),
				'--max_upload_rate', str(self.bt_settings['ul_limit'])]
				
			import BTDownloader
			downloader = BTDownloader.BTDownloader(media, self.media_dir, params,True, queue, self.callback_progress,self.callback_finished)
			self.downloads.append(downloader)
			self.pool.queueTask(downloader.download)
		else: #http regular download
			ext = os.path.splitext(media['file'])[1]
			if len(ext)>5 or len(ext)==0:
				#I think this isn't really the right extension.   See fucking ask a ninja: http://feeds.feedburner.com/AskANinja
				try:
					import mimetypes
					real_ext = mimetypes.guess_extension(media['mimetype'])
					if real_ext is not None:
						media['file']=media['file']+real_ext
				except:
					print "ERROR couldn't guess mimetype, leaving filename alone"
			import HTTPDownloader
			downloader = HTTPDownloader.HTTPDownloader(media, self.media_dir, None, resume, queue, self.callback_progress, self.callback_finished)
			self.downloads.append(downloader)
			self.pool.queueTask(downloader.download)
			
		self.db.set_media_download_status(media['media_id'],1)
		self.db.set_media_filename(media['media_id'],media['file'])
		self.index=self.index+1
		
	def has_downloader(self, media_id):
		for download in self.downloads:
			if download.media['media_id'] == media_id:
				return True
		return False
		
	def get_downloader(self, media_id):
		for download in self.downloads:
			if download.media['media_id'] == media_id:
				return download
		raise DownloadNotFound, media_id
		
	def get_download_list(self, status=None):
		list = []
		
		if status is not None:
			list = [d for d in self.downloads if d.status == status]
		else:
			list = copy.copy(self.downloads)
		return list
		
	def _basic_finished_callback(self, data):
		print data
		self.db.set_media_download_status(data[0]['media_id'],ptvDB.D_DOWNLOADED)	
			
	def _basic_progress_callback(self, data):
		print os.path.split(data[0]['file'])[1]+" "+data[2]
		
	def callback_progress(self, obj):
		#print "mediamanager progress"
		return self.app_callback_progress(obj)
	
	def callback_finished(self, obj):
		if obj.status in [STOPPED, FINISHED, FINISHED_AND_PLAY, FAILURE]:
			try:
				self.downloads.remove(obj)
			except:
				print "Warning: couldn't remove download"
		self.update_playlist(obj.media)
		#if self.pause_state == RUNNING:
		self.app_callback_finished(obj)
			
	def get_download_count(self):
		try:
			#return self.pool.getTaskCount()
			return len(self.downloads)
		except:
			return 0
		
	def pause_all_downloads(self):
		#print "downloads paused"
		#try:
		if self.pause_state == RUNNING:
			for download in self.downloads:
				download.stop()
				#if not download.status == Downloader.DOWNLOADING: #send signal for all queued downloads
				#	self.finished_callback(download, (download.media,MediaManager.STOPPED,None)) 
			self.pool.joinAll(False,True) #don't wait for tasks, but let the threads die naturally
			if not self.quitting:
				self.pool.setThreadCount(5)
			#reset
			self.downloads = []
			self.pause_state = PAUSED
		#except:
		#	pass
		
	def unpause_downloads(self):
		"""DOES NOT requeue downloads.  Just clears the state"""
		self.pause_state = RUNNING
		
	def stop_download(self, media_id):
		if self.has_downloader(media_id):
			downloader = self.get_downloader(media_id)
			downloader.stop()
			
	def get_disk_usage(self):
		size = 0
		try:
			#filelist = glob.glob(self.media_dir+"/*")
			for f in utils.GlobDirectoryWalker(os.path.join(self.media_dir, "")):
				size = size+os.stat(f)[6]
		except:
			pass
		return size
		
	def generate_playlist(self):
		dated_dir = utils.get_dated_dir()
		try:
			os.stat(os.path.join(self.media_dir, dated_dir))
		except:
			os.mkdir(os.path.join(self.media_dir, dated_dir))
		f = open(os.path.join(self.media_dir, dated_dir, "playlist.m3u"),'w')
		f.write('#EXTM3U\n')
		
		for item in glob.glob(os.path.join(self.media_dir, dated_dir, "*")):
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
			os.stat(os.path.join(self.media_dir, dated_dir, "playlist.m3u"))
			f = open(os.path.join(self.media_dir, dated_dir, "playlist.m3u"),'a')
		except:
			f = open(os.path.join(self.media_dir, dated_dir, "playlist.m3u"),'w')
			f.write('#EXTM3U\n')
		
		f.write(os.path.split(media['file'])[1]+"\n")
		f.close()

class NoDir(Exception):
	def __init__(self,durr):
		self.durr = durr
	def __str__(self):
		return "no such directory: "+self.durr
		
class DownloadNotFound(Exception):
	def __init__(self,durr):
		self.durr = durr
	def __str__(self):
		return "download not found: "+str(self.durr)
