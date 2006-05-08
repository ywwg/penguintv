class Downloader:
	"""Interface class for downloading.  Doesn't do anything"""
	def __init__(self, media, media_dir, params, resume, queue, progress_callback=None, finished_callback=None):
		#no params
		self.media = media
		if progress_callback is not None:
			self.progress_callback = progress_callback
		else:
			self.progress_callback = self._basic_progress_callback
		if finished_callback is not None:
			self.finished_callback = finished_callback
		else:
			self.finished_callback = self._basic_finished_callback
		self.resume = resume
		self.queue = queue
		
	def download(self,args):
		"""args is set by ThreadPool, and is unused"""
		print "The Downloader base class does not implement this method"
		
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
