# Written by Owen Williams
# see LICENSE for license information
import pycurl
import threading

class SimpleImageCache:
	"""Dead simple.  we keep all of the images _in_ram_ with a dictionary. OH YEAH"""
	
	def __init__(self):
		self.image_dict={}
		self.thread_list = []
		
	def get_image(self, entry_id, url, stream):
		t = self.downloader(entry_id, url,stream, self.image_dict)
		self.thread_list.append(t)
		t.start()
		
	def quit_entry(self, entry_id):
		print "aborting "+str(entry_id)
		for t in self.thread_list:
			if t.entry_id == entry_id:
				print "setting some thread to quit"
				t.quit=1
				t.join()
		
	class downloader(threading.Thread):
		def __init__(self, entry_id, url, stream, image_dict):
			threading.Thread.__init__(self)
			self.contents = ''
			self.quit = 0 
			self.entry_id = entry_id
			self.url = url
			self.stream = stream
			self.image_dict = image_dict
			
		def run(self):
			if len(self.image_dict) > 100:  #flush it every so often
				del self.image_dict
				self.image_dict = {}
			if self.image_dict.has_key(self.url):
				#if self.image_dict[self.url]=="":
				#	print "image not cached nicely"
					#raise
				return self.image_dict[self.url]
			else:
				c = pycurl.Curl()
				c.setopt(c.URL, self.url)
				c.setopt(c.WRITEFUNCTION, self.body_callback)
				c.setopt(pycurl.CONNECTTIMEOUT, 7) #aggressive timeouts
				c.setopt(pycurl.TIMEOUT, 20) #aggressive timeouts
				c.setopt(pycurl.PROGRESSFUNCTION, self.progress_callback)
				try:
					c.perform()
					c.close()
				except:
					print "exception"
					self.image_dict[self.url]=""
				self.image_dict[self.url]=self.contents
				self.stream.write(self.contents)
				self.stream.close()

		def body_callback(self, buf):
			self.contents = self.contents + buf
			
		def progress_callback(self, dl_total, dl_now, ul_total, ul_now):
			print "progress"
			return self.quit
