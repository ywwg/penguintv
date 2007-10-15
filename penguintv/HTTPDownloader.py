import logging
import time

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
		self._resume_from = 0
		self._last_progress = 0
		
	def download(self,args_unused):
		Downloader.download(self,args_unused)
		try:
			os.makedirs(os.path.dirname(self.media['file']))
		except OSError:
			pass
		try:
			if self._resume:
				try:
					fp = open(self.media['file'], "ab")
				except:
					fp = open(self.media['file'], "wb")
			else:
				fp = open(self.media['file'], "wb")
			curl = pycurl.Curl()
			curl.setopt(pycurl.URL, str(self.media['url']).strip()) #cause it's unicode or some shit which is not a string or some junk.  Also strip whitespace
			curl.setopt(pycurl.FOLLOWLOCATION, 1)
			curl.setopt(pycurl.MAXREDIRS, 5)
			curl.setopt(pycurl.CONNECTTIMEOUT, 30)
			curl.setopt(pycurl.NOSIGNAL, 1)
			curl.setopt(pycurl.WRITEDATA, fp)
			curl.setopt(pycurl.PROGRESSFUNCTION, self._wrap_progress_callback)
			curl.setopt(pycurl.NOPROGRESS, 0)
			curl.setopt(pycurl.USERAGENT,'PenguinTV '+utils.VERSION)
			if self._resume:
				self._resume_from = os.stat(self.media['file'])[6]
				curl.setopt(pycurl.RESUME_FROM_LARGE, self._resume_from)
			curl.perform()
			response = curl.getinfo(pycurl.RESPONSE_CODE)
			curl.close()
			fp.close()
			if self.media['url'][:5] == "http:":
				if response != 200 and response != 206:
					if response == 404:
						self.media['errormsg']=_("404: File Not Found")
					else:
						d = {"response":response}
						self.media['errormsg']=_("Some HTTP error: %(response)s") % d
					self.status = FAILURE
					self.message = self.media['errormsg']
					self._finished_callback()
					return
			elif self.media['url'][:5] == "file:":
				pass #it's ok, curl would throw an exception on error
			elif self.media['url'][:4] == "ftp:":
				major_code = response / 100
				if major_code == 2: #positive reply
					pass
				elif major_code == 4 or major_code == 5:
					d = {"response":response}
					self.media['errormsg']=_("FTP error: %(response)s") % d
				else:
					d = {"response":response}
					self.media['errormsg']=_("Unexpected FTP response: %(response)s") % d
			else: 
				self.media['errormsg']=_("Unknown protocol")
				self.status = FAILURE
				self.message = self.media['errormsg']
				self._finished_callback()
				return
			
			if self._queue:
				self.status = FINISHED_AND_PLAY
				self.message = _("finished downloading %s") % self.media['file']
				self._finished_callback()
				return
			self.status = FINISHED
			self.message = _("finished downloading %s") % self.media['file']
			self._finished_callback()
		except Exception, data: #this can happen if we cancelled the download
			if data[0]==33: #if server doesn't support resuming, retry
				self._resume=False
				self.download(None)
			elif data[0]==42:
				if self.status not in [STOPPED, PAUSED]:
					self.status = STOPPED
				self.message = ""
				self._finished_callback()
			else:
				print "some downloading error "+str(data),self.media
				self.media['errormsg']=data
				self.status = FAILURE
				self.message = data
				self._finished_callback()
		
	def _wrap_progress_callback(self, dl_total, dl_now, ul_total, ul_now):
		now = time.time()
		if now - self._last_progress < 2.0:
			return
		self._last_progress = now
		if self._resume: #adjust sizes so that the percentages are correct
			dl_total += self._resume_from
			dl_now   += self._resume_from
		try:
			self.progress = int((dl_now*100.0)/dl_total)
		except:
			self.progress = 0	
		if not self.media.has_key('size'):
			self.media['size_adjustment']=True
		elif self.media['size']!=round(dl_total) and not self._resume:
			self.media['size']=round(dl_total)
			self.media['size_adjustment']=True
		else:
			self.media['size_adjustment']=False
		d = { 'progress': str(self.progress),
			  'size': utils.format_size(self.media['size'])}
		self.total_size = self.media['size']
		if self.total_size == 0:
			d['dl_now'] = dl_now
			self.message = _("Downloaded %(dl_now)s...") % d
		else:
			self.message = _("Downloaded %(progress)s%% of %(size)s") % d
		return self._progress_callback()
