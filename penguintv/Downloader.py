QUEUED            = 0
DOWNLOADING       = 1
FINISHED          = 2
FINISHED_AND_PLAY = 3
STOPPED           = 4
FAILURE           = -1

class Downloader:
	"""Interface class for downloading.  Doesn't do anything"""
	def __init__(self, media, media_dir, params, resume, queue, progress_callback=None, finished_callback=None):
		#no params
		if progress_callback is not None:
			self.app_progress_callback = progress_callback
		else:
			self.app_progress_callback = self._basic_progress_callback
		if finished_callback is not None:
			self.app_finished_callback = finished_callback
		else:
			self.app_finished_callback = self._basic_finished_callback
		self.resume = resume
		self.queue = queue
		self.progress = 0
		self.total_size = 1
		self.media = media
		self.status = QUEUED
		self.message = ""
		self._stop_download = False
			
	def download(self,args):
		"""args is set by ThreadPool, and is unused"""
		#print "The Downloader base class does not implement this method"
		self.running = True
		self.status = DOWNLOADING
		
	def progress_callback(self):
		print self.media['media_id'],self.progress,self.total_size
		if self._stop_download:
			self.app_progress_callback(self)
			return 1
		return self.app_progress_callback(self)
		
	def finished_callback(self):
		return self.app_finished_callback(self)
		
	def stop(self):
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
