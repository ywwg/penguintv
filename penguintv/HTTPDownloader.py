from Downloader import *

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

class HTTPDownloader(Downloader):
	"""Need a little internal class to keep track of callbacks from urllib.urlretrieve"""
	def __init__(self, media, media_dir, params, resume, queue, progress_callback, finished_callback):
		Downloader.__init__(self, media, media_dir, params, resume, queue, progress_callback, finished_callback)
		#no params
		self.resume_from = 0
		
	def download(self,args_unused):
		Downloader.download(self,args_unused)
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
				self.status = FAILURE
				self.message = self.media['errormsg']
				self.finished_callback(self)
				return
			
			if self.queue:
				self.status = FINISHED_AND_PLAY
				self.message = _("finished downloading %s") % self.media['file']
				self.finished_callback()
				return
			self.status = FINISHED
			self.message = _("finished downloading %s") % self.media['file']
			self.finished_callback()
		except Exception, data: #this can happen if we cancelled the download
			if data[0]==33: #if server doesn't support resuming, retry
				self.resume=False
				self.download(None)
			if data[0]==42:
				self.status = STOPPED
				self.message = ""
				self.finished_callback()
			else:
				print "some downloading error "+str(data)
				self.media['errormsg']=data
				self.status = FAILURE
				self.message = data
				self.finished_callback()
		
	def wrap_progress_callback(self, dl_total, dl_now, ul_total, ul_now):
		if self.resume: #adjust sizes so that the percentages are correct
			dl_total += self.resume_from
			dl_now   += self.resume_from
		try:
			self.progress = int((dl_now*100.0)/dl_total)
		except:
			self.progress = 0	
		if self.media.has_key('size')==False:
			self.media['size_adjustment']=True
		elif self.media['size']!=round(dl_total) and self.resume==False:
			self.media['size']=round(dl_total)
			self.media['size_adjustment']=True
		else:
			self.media['size_adjustment']=False
		d = { 'progress': str(self.progress),
			  'size': utils.format_size(self.media['size'])}
		self.total_size = self.media['size']
		self.message = _("Downloaded %(progress)s%% of %(size)s") % d
		return self.progress_callback()
