# Written by Owen Williams
# see LICENSE for license information
import pycurl

class SimpleImageCache:
	"""Dead simple.  we keep all of the images _in_ram_ with a dictionary. OH YEAH"""
	
	def __init__(self):
		self.image_dict={}
		
	def is_cached(self, url):
		if self.image_dict.has_key(url):
			return True
		return False
		
	def get_image(self, url):
		if len(self.image_dict) > 100:  #flush it every so often
			del self.image_dict
			self.image_dict = {}
		if self.image_dict.has_key(url):
			#if self.image_dict[url]=="":
			#	print "image not cached nicely"
				#raise
			return self.image_dict[url]
		else:
			d = SimpleImageCache.downloader()
			c = pycurl.Curl()
			c.setopt(c.URL, url)
			c.setopt(c.WRITEFUNCTION, d.body_callback)
			c.setopt(pycurl.CONNECTTIMEOUT, 7) #aggressive timeouts
			c.setopt(pycurl.TIMEOUT, 20) #aggressive timeouts
			try:
				c.perform()
				c.close()
			except:
				self.image_dict[url]=""
			self.image_dict[url]=d.contents
			return d.contents
			
	class downloader:
		def __init__(self):
			self.contents = ''

		def body_callback(self, buf):
			self.contents = self.contents + buf
