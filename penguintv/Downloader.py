QUEUED            = 0
DOWNLOADING       = 1
FINISHED          = 2
FINISHED_AND_PLAY = 3
STOPPED           = 4
PAUSED            = 5
FAILURE           = -1

#import traceback
import gobject

class Downloader:
	"""Interface class for downloading.  Doesn't do anything"""
	def __init__(self, media, media_dir, params, resume, queue, progress_callback=None, finished_callback=None):
		#no params
		if progress_callback is not None:
			self._app_progress_callback = progress_callback
		else:
			self._app_progress_callback = self._basic_progress_callback
		if finished_callback is not None:
			self._app_finished_callback = finished_callback
		else:
			self._app_finished_callback = self._basic_finished_callback
		self._resume = resume
		self._queue = queue
		self._media_dir = media_dir
		self._stop_download = False
		
		self.media = media
		self.status = QUEUED
		self.message = ""
		self.progress = 0
		self.total_size = 1
			
	def download(self,args):
		"""args is set by ThreadPool, and is unused"""
		if self._stop_download:
			return False
		
		self.running = True
		self.status = DOWNLOADING
		return True
		
	def _progress_callback(self):
		if self._stop_download:
			self._app_progress_callback(self)
			return 1
		return self._app_progress_callback(self)
		
	def _finished_callback(self):
		return self._app_finished_callback(self)
		
	def pause(self):
		self.status = PAUSED
		self._stop_download = True
		
	def stop(self):
		self.status = STOPPED
		if self._stop_download: #if it's called _again_, ping the app and say "we're done already!"
			return self._app_finished_callback(self)
		self._stop_download = True
		
	def _basic_finished_callback(self, data):
		filename = data[0]['file']
		info = data[1:]
		print filename+" "+str(info)
			
	def _basic_progress_callback(self, data):
		media, blocks, blocksize, totalsize=data
		percent = (blocks*blocksize*100) / totalsize
		if percent>100:
			percent = 100
		if percent%10 == 0:
			print media['file']+" "+str(percent)+"%"
