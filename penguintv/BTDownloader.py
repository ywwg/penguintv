# Written by Owen Williams
# see LICENSE for license information

from Downloader import *

from ptvbittorrent import download
from threading import Event
import time
import os, os.path
import ptvDB
import utils
import timeoutsocket
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
		
class BTDownloader(Downloader):
	def __init__(self, media, media_dir, bt_params="", resume=False, queue=1, progress_callback=None, finished_callback=None):
	#self.progress_callback((self.media,blocks,blocksize,totalsize))
				#return (self.media, 2,"finished downloading "+self.media['file'])				0 is failure, 1 is success, 2 is success and queue
		#bit torrent always resumes if it can.
		Downloader.__init__(self, media, media_dir, params, resume, queue, progress_callback, finished_callback)
		self.media_dir = media_dir
		self.bt_params = bt_params
		self.totalsize=0
		self.done = Event()
		self.start_time=time.time()
		self.last_update=self.start_time
		self.downTotal=0
		self.done_downloading = False
				
	def download(self,args_unused):
		Downloader.download(self,args_unused)
		#print "bt ready to download: "+str(self.media['url'])
		#download(params, h.chooseFile, h.display, h.finished, h.error, Event(), cols, h.newpath)
		params = ['--url' ,self.media['url']]+self.bt_params
		
		try:
			download.download(params,  self.chooseFile, self.display, self.normalize_finished, self.error, self.done, 80, self.newpath)
		except timeoutsocket.Timeout, detail:
			self.media['errormsg'] = str(detail)
			self.finished_callback((self.media,MediaManager.FAILURE,detail))		
		except:
			self.media['errormsg'] = _("There was an error downloading the torrent")
			self.finished_callback((self.media,MediaManager.FAILURE,_("There was an error downloading the torrent")))
		self.finished_callback(self, (self.media,MediaManager.STOPPED,None))

	def chooseFile(self, default, size, saveas, dir):
		self.totalsize=size
		dated_dir = utils.get_dated_dir()
		change=0
		if self.media['size']!=self.totalsize:
			self.media['size']=self.totalsize
			change = 1
		if self.media['file']!=self.media_dir+"/"+dated_dir+"/"+str(default):
			self.media['file']=self.media_dir+"/"+dated_dir+"/"+str(default)
			#print "changed to"+str(self.media['file'])			
			change = 1
		if change:
			db = ptvDB.ptvDB()
			db.set_media_filename(self.media['media_id'],self.media['file'])
			db.set_media_size(self.media['media_id'],self.media['size'])
			db.finish()
			del db
		return self.media_dir+"/"+dated_dir+"/"+str(default)
	
	def display(self, dict):
		if dict.has_key('downTotal'):
			self.downTotal = dict['downTotal']
		
		if dict.has_key('fractionDone'):
		#	current_time = time.time()
		#	if current_time - self.last_update > 2: #don't update more than once every 2 seconds
		#	self.last_update = current_time
			progress = int(dict['fractionDone']*100.0)
			d = {'progress':str(progress),
				 'size':utils.format_size(self.totalsize)
				 }
			if dict.has_key('timeEst'):
				d['time']=utils.hours(dict['timeEst'])
				progress_message = _("Downloaded %(progress)s%% of %(size)s, %(time)s remaining.") % d
			else:
				progress_message = _("Downloaded %(progress)s%% of %(size)s") % d
			
			if self.progress_callback(self, (self.media,progress,progress_message)) == 1:
				self.done.set() 
				
		else:
			progress = 0
			progress_message = ""
			if self.progress_callback(self, (self.media,progress,progress_message)) == 1:
				self.done.set()
		
		if dict.has_key('upTotal'): #check to see if we should stop
			if self.done_downloading == True:
				if dict['upTotal'] >= self.downTotal: #if ratio is one, quit
					self.done.set()
				if time.time() - 60*60 >= self.start_time: #if it's been an hour, quit
					self.done.set()
		
	def normalize_finished(self):
		if self.queue==True:
			q = MediaManager.FINISHED_AND_PLAY
		else:
			q = MediaManager.FINISHED
		self.finished_callback(self, (self.media, q,"finished downloading "+self.media['file']))			
		self.done_downloading = True
		#don't stop uploading, we keep going until 1:1 or one hour
		#FIXME: deal with directories just in case

		
	def error(self, errormsg):
		#for some reason this isn't a fatal error
		if errormsg!='rejected by tracker - This tracker requires new tracker protocol. Please use our Easy Downloader or check blogtorrent.com for updates.':
			print "error: "+errormsg
			self.media['errormsg']=errormsg
			self.finished_callback(self, (self.media,MediaManager.FAILURE,errormsg))		
			self.done.set()
		else:
			print "getting blogtorrent 'rejected by tracker' error, ignoring"

		
	def newpath(self, path):
		pass
		#print "new path?: " +path
		

class NoDir(Exception):
	def __init__(self,durr):
		self.durr = durr
	def __str__(self):
		return "no such directory: "+self.durr
