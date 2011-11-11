# Written by Owen Williams
# see LICENSE for license information

import ptvDB
from types import *
import ThreadPool
import time
import os,os.path
import copy
import logging
import shutil
import re

import Downloader
#import BTDownloader  loaded when needed
#import HTTPDownloader  loaded when needed

from utils import format_size

import utils

if utils.RUNNING_HILDON:
	HAS_GNOME = False
else:
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

BYDATE = 0
BYNAME = 1

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
	def __init__(self, app, media_dir, progress_callback=None, finished_callback=None):
		self.index=0
		#should this be lucene compatible?
		if utils.RUNNING_HILDON:
			max_downloads = 1
		else:
			max_downloads = 5
		self._style=BYDATE
		self.pool = ThreadPool.ThreadPool(max_downloads, "MediaManager")
		self.downloads = []
		self.db = app.db
		self.time_appendix=0
		self.bt_settings = {'min_port':6881, 'max_port':6999, 'ul_limit':0}
		self.id_time=0
		self.quitting = False
		self._net_connected = True
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
		
		if media_dir[0] == '~':
			media_dir = os.getenv('HOME') + media_dir[1:]
		
		try:
			os.stat(media_dir)
		except:
			try:
				os.mkdir(media_dir)
			except:
				raise NoDir, "error creating " +media_dir
		self._media_dir = media_dir
		
		app.connect('online-status-changed', self.__online_status_changed)
		app.connect('new-database', self.__new_database_cb)
	
	def finish(self):
		self.quitting = True
		try:
			self.pool.joinAll()
			del self.pool
		except:
			pass
		
	def __del__(self):
		self.finish()
		
	def set_media_dir(self, new_dir):
		"""sets new media dir.  returns None, None on success, and returns new dir name
		if db and player need to be remapped to new dirs"""
		old_dir = self._media_dir
		if new_dir == old_dir:
			return None, None
		std_loc = os.path.join(utils.get_home(), 'media')
			
		#stat new folder
		if not os.access(new_dir, os.F_OK & os.R_OK & os.W_OK & os.X_OK):
			raise NoDir, "insufficient permissions to access %s" % new_dir
			
		try:
			os.symlink
			HAVE_SYMLINK = True
		except:
			HAVE_SYMLINK = False	
			
		if HAVE_SYMLINK:
			if old_dir == std_loc:
				self._move_contents(std_loc, new_dir)
				self._media_dir = new_dir
				if os.path.islink(std_loc):
					os.remove(std_loc)
					os.symlink(new_dir, std_loc)
				else:
					os.rmdir(std_loc)
					os.symlink(new_dir, std_loc)
					return old_dir, std_loc
			elif new_dir == std_loc:
				self._media_dir = std_loc
				if os.path.islink(std_loc):
					os.remove(std_loc)
					self._move_contents(old_dir, std_loc)
				else:
					os.rmdir(std_loc)
					os.mkdir(std_loc)
					self._move_contents(old_dir, std_loc)
					return old_dir, std_loc
			else:
				self._move_contents(old_dir, new_dir)
				self._media_dir = new_dir
				if os.path.islink(std_loc):
					os.remove(std_loc)
					os.symlink(new_dir, std_loc)
				else:
					os.rmdir(std_loc)
					os.symlink(new_dir, std_loc)
					return old_dir, std_loc
		else:
			self._move_contents(old_dir, new_dir)
			self._media_dir = new_dir
			return old_dir, new_dir
				
		return None, None
			
	def _move_contents(self, src, dst):
		p = re.compile("\d{4}-\d{2}-\d{2}$")
		for f in os.listdir(src):
			if p.search(f) is not None or f.upper().endswith('M3U'):
				shutil.move(os.path.join(src, f), os.path.join(dst, f))
			
	def get_media_dir(self):
		return self._media_dir
		
	def __online_status_changed(self, app, connected):
		if not connected:
			app.pause_downloads()
		else:
			if not self._net_connected:
				self.unpause_downloads()
				app.resume_resumable()

		self._net_connected = connected
		
	def __new_database_cb(self, app, db):
		self.db = db
		
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
		if self._style==BYDATE:
			url = "file://"+self._media_dir+"/"+utils.get_dated_dir()
		else:
			url = "file://"+self._media_dir
		if HAS_GNOME:
			gnome.url_show(url)
		else:
			import webbrowser
			webbrowser.open_new_tab(url)
					
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
		media['feedname'] = self.db.get_feed_title(media['feed_id'])
		media['downloader_index']=self.index
		media['download_status']=1
		media.setdefault('size',0)			
		if media['file'] is None:
		#logging.debug("TEMP OVERRIDE OF FILENAME?")
		#if True:
			filename = os.path.basename(media['url'])
			filen, ext = os.path.splitext(filename)
			ext = ext.split('?')[0] #grrr lugradio...
			#media['file']=os.path.join(self._media_dir, utils.get_dated_dir(), filen+ext)
			media['file']=self.get_storage_dir(media, filen+ext)
			dated_dir = os.path.split(os.path.split(media['file'])[0])[1]
			try: #make sure
				os.stat(os.path.join(self._media_dir, dated_dir))
			except:
				os.mkdir(os.path.join(self._media_dir, dated_dir))
			if self.db.media_exists(media['file']): #if the filename is in the db, rename
				#media['file']=os.path.join(self._media_dir, utils.get_dated_dir(), filen+"-"+self.get_id()+ext)
				media['file']=self.get_storage_dir(media, filen+"-"+self.get_id()+ext)
			else:
				try:
					os.stat(media['file'])  #if this raises exception, the file doesn't exist and we're ok
					#media['file']=os.path.join(self._media_dir, utils.get_dated_dir(), filen+"-"+self.get_id()+ext) #if not, get new name
					media['file']=self.get_storage_dir(media, filen+"-"+self.get_id()+ext) #if not, get new name
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
			downloader = BTDownloader.BTDownloader(media, self._media_dir, params,True, queue, self.callback_progress,self.callback_finished)
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
			downloader = HTTPDownloader.HTTPDownloader(media, self._media_dir, None, resume, queue, self.callback_progress, self.callback_finished)
			self.downloads.append(downloader)
			self.pool.queueTask(downloader.download)
			
		#self.db.set_media_download_status(media['media_id'],1)
		#self.db.set_media_filename(media['media_id'],media['file'])
		self.db.set_media(media['media_id'], status=1, filename=media['file'])
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
				print "Warning: couldn't remove download", obj.media
		self.update_playlist(obj.media)
		#if self.pause_state == RUNNING:
		self.app_callback_finished(obj)
			
	def get_download_count(self):
		try:
			#return self.pool.getTaskCount()
			return len(self.downloads)
		except:
			return 0
		
	def stop_all_downloads(self):
		#try:
		if self.pause_state == RUNNING:
			for download in self.downloads:
				download.stop()
				#if not download.status == Downloader.DOWNLOADING: #send signal for all queued downloads
				#	self.finished_callback(download, (download.media,MediaManager.STOPPED,None)) 
			try:
				self.pool.joinAll(False,True) #don't wait for tasks, but let the threads die naturally
			except AttributeError:
				logging.warning("no pool to delete, no problem")
			#reset
			self.downloads = []
			self.pause_state = PAUSED
		#except:
		#	pass

	def pause_all_downloads(self):
		if self.pause_state == RUNNING:
			for download in self.downloads:
				download.pause()
			self.pool.joinAll(False,True) #don't wait for tasks, but let the threads die naturally
			self.pause_state = PAUSED
		
	def unpause_downloads(self):
		"""DOES NOT requeue downloads.  Just clears the state"""
		self.pause_state = RUNNING
		
	def stop_download(self, media_id):
		if self.has_downloader(media_id):
			downloader = self.get_downloader(media_id)
			if downloader.status == QUEUED:
				#if it's queued, we can stop it directly
				#the threadpool will still hold on to the object, but 
				#when it tries to run it will see that it has been stopped
				downloader.stop()
				self.update_playlist(downloader.media)
				self.app_callback_finished(downloader)
				self.downloads.remove(downloader)
			else:
				downloader.stop()
			
	def get_disk_usage(self):
		#this is much faster on maemo, which sucks at mmc disk access
		#trying this all the time now, it's just better
		import subprocess
		if not os.path.isdir(self._media_dir):
			return 0
		
		size = 0
		try:
			cmd = "du -sk %s" % self._media_dir
			p = subprocess.Popen(cmd, shell=True, close_fds=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
			retval = p.wait()
			stderr = p.stderr.read()
			if len(stderr) > 1 or retval != 0:
				return 0
			retval = p.stdout.read().split('\t')[0]
			size = long(retval)*1024L
		except:
			#fall back on old method
			try:
				for f in utils.GlobDirectoryWalker(self._media_dir):
					size = size+os.stat(f)[6]
			except:
				return 0
		return size
		
	def generate_playlist(self):
		if utils.RUNNING_SUGAR:
			return
		if self._style == BYDATE:
			import glob
			dated_dir = utils.get_dated_dir()
			try:
				os.stat(os.path.join(self._media_dir, dated_dir))
			except:
				os.mkdir(os.path.join(self._media_dir, dated_dir))
			f = open(os.path.join(self._media_dir, dated_dir, "playlist.m3u"),'w')
			f.write('#EXTM3U\n')
		
			for item in glob.glob(os.path.join(self._media_dir, dated_dir, "*")):
				filename = os.path.split(item)[1]
				if filename != "playlist.m3u":
					f.write(filename+"\n")
			f.close()
		
	def update_playlist(self, media):
		"""Adds media to the playlist in its directory"""
		
		if utils.RUNNING_SUGAR:
			return
		
		try:
			os.stat(media['file'])
		except:
			return
			
		dated_dir = os.path.split(os.path.split(media['file'])[0])[1]
			
		try:
			os.stat(os.path.join(self._media_dir, dated_dir, "playlist.m3u"))
			f = open(os.path.join(self._media_dir, dated_dir, "playlist.m3u"),'a')
		except:
			f = open(os.path.join(self._media_dir, dated_dir, "playlist.m3u"),'w')
			f.write('#EXTM3U\n')
		
		f.write(os.path.split(media['file'])[1]+"\n")
		f.close()
		
	def set_storage_style(self, style, migrate=False):
		if self._style == style:
			return
		self._style = style
		if migrate:
			#migrate the media from one style to the other
			if self._style == BYDATE:
				self.db.set_media_storage_style_dated(self._media_dir)
			else:
				self.db.set_media_storage_style_named(self._media_dir)
			
	def get_storage_style(self):
		return self._style
		
	def get_storage_dir(self, media, filename):
		if self._style == BYDATE:
			return os.path.join(self._media_dir, utils.get_dated_dir(), filename)
		elif self._style == BYNAME:
			return os.path.join(self._media_dir, utils.make_pathsafe(media['feedname']), filename)
		else:
			logging.error("Bad storage style (not 0 or 1): %i" % self._style)
			assert False

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
