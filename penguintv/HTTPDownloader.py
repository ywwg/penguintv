import ptvDB
import pycurl
import utils
import os
#import time
import MediaManager


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
#              where status is 0=failed, 1=success, 2=success and queue

class HTTPDownloader:
	"""Need a little internal class to keep track of callbacks from urllib.urlretrieve"""
	def __init__(self, media, media_dir, params, resume, queue, progress_callback, finished_callback):
		#no params
		self.media = media
		self.progress_callback = progress_callback
		self.finished_callback = finished_callback
		self.resume = resume
		self.resume_from = 0
		self.queue = queue
		
	def download(self,args_unused):
		try:
			os.makedirs(os.path.dirname(self.media['file']))
		except OSError:
			pass
		try:
			if self.resume:
				try:
					fp = open(self.media['file'], "ab")
				except:
					fp = open(self.media['file'], "wb")
			else:
				fp = open(self.media['file'], "wb")
			curl = pycurl.Curl()
			curl.setopt(pycurl.URL, str(self.media['url'])) #cause it's unicode or some shit which is not a string or some junk
			curl.setopt(pycurl.FOLLOWLOCATION, 1)
			curl.setopt(pycurl.MAXREDIRS, 5)
			curl.setopt(pycurl.CONNECTTIMEOUT, 30)
			curl.setopt(pycurl.NOSIGNAL, 1)
			curl.setopt(pycurl.WRITEDATA, fp)
			curl.setopt(pycurl.PROGRESSFUNCTION, self.wrap_progress_callback)
			curl.setopt(pycurl.NOPROGRESS, 0)
			curl.setopt(pycurl.USERAGENT,'PenguinTV '+utils.VERSION)
			if self.resume:
				self.resume_from = os.stat(self.media['file'])[6]
				curl.setopt(pycurl.RESUME_FROM_LARGE, self.resume_from)
			curl.perform()
			response = curl.getinfo(pycurl.RESPONSE_CODE)
			curl.close()
			fp.close()
				
			if response != 200 and response != 206:
				if response == 404:
					self.media['errormsg']=_("404: File Not Found")
				else:
					d = {"response":response}
					self.media['errormsg']=_("Some HTTP error: %(response)s") % d
				self.finished_callback((self.media,MediaManager.FAILURE,self.media['errormsg']))
				return
			
			if self.queue:
				self.finished_callback((self.media, MediaManager.FINISHED_AND_PLAY,_("finished downloading %s") % self.media['file']))
			self.finished_callback((self.media, MediaManager.FINISHED,_("finished downloading %s") % self.media['file']))
		except Exception, data: #this can happen if we cancelled the download
			if data[0]==33: #if server doesn't support resuming, retry
				self.resume=False
				self.download(None)
			if data[0]==42:
				self.finished_callback((self.media,MediaManager.STOPPED,None))
			else:
				print "some downloading error "+str(data)
				self.media['errormsg']=data
				self.finished_callback((self.media,MediaManager.FAILURE,data))
		
	def wrap_progress_callback(self, dl_total, dl_now, ul_total, ul_now):
		#current_time = time.time()
		#if current_time - self.last_update > 2: #update only once every 2 seconds
	#	self.last_update = current_time
		if self.resume: #adjust sizes so that the percentages are correct
			dl_total += self.resume_from
			dl_now   += self.resume_from
		try:
			progress = int((dl_now*100.0)/dl_total)
		except:
			progress = 0	
		if self.media.has_key('size')==False:
			self.media['size']=round(dl_total)
			self.media['size_adjustment']=True
		elif self.media['size']!=round(dl_total) and self.resume==False:
			self.media['size']=round(dl_total)
			self.media['size_adjustment']=True
		else:
			self.media['size_adjustment']=False
		d = { 'progress': str(progress),
			  'size': utils.format_size(self.media['size'])}
		return self.progress_callback((self.media,progress,_("Downloaded %(progress)s%% of %(size)s") % d))
		#return result
		#return 0
