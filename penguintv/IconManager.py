import os, os.path
import glob
import urllib

class IconManager:

	"""A small class that handles favicons for feeds"""

	def __init__(self, home):
		self._home = home
		try:
			os.stat(os.path.join(self._home, 'icons'))
		except:
			os.mkdir(os.path.join(self._home, 'icons'))

	def icon_exists(self, feed_id):
		filename = os.path.join(self._home, 'icons', str(feed_id) + '.*')
		result = glob.glob(filename)
		result = [r for r in result if r[-4:].upper() != "NONE"]
		return result > 0	
		
	def get_icon(self, feed_id):
		filename = os.path.join(self._home, 'icons', str(feed_id) + '.*')
		result = glob.glob(filename)
		if len(result) == 0:
			return None
		return result[0]
	
	def get_icon_pixbuf(self, feed_id, max_width=None, max_height=None, min_width=None, min_height=None):
		import gtk
		filename = self.get_icon(feed_id)
		if filename is None:
			p = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB,True,8, min_width, min_height)
			p.fill(0xffffff00)
			return p
	
		try:
			p = gtk.gdk.pixbuf_new_from_file(filename)
		except:
			p = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB,True,8, min_width, min_height)
			p.fill(0xffffff00)
			return p
		height = p.get_height()
		width = p.get_width()
		if max_height is not None:
			if height > max_height:
				height = max_height
				width = p.get_width() * height / p.get_height()
		if max_width is not None:
			if width > max_width:
				width = max_width
				height = p.get_height() * width / p.get_width()
		if min_height is not None:
			if height < min_height:
				height = min_height
				width = p.get_width() * height / p.get_height()
		
		if min_width is not None:
			if width < min_width:
				width = min_width
				height = p.get_height() * width / p.get_width()
		
		if height != p.get_height() or width != p.get_width():
			del p
			p = gtk.gdk.pixbuf_new_from_file_at_size(filename, width, height)
		return p
		
	def download_icon(self, feed_id, feedparser_data):
		url_list = []
		try: url_list.append(feedparser_data['feed']['image']['href'])
		except: pass
		
		try: url_list.append(feedparser_data['feed']['link'] + '/favicon.ico')
		except: pass
		
		for url in url_list:
			try:
				filename = os.path.join(self._home, 'icons', str(feed_id) + '.' + url.split('.')[-1])
				urllib.urlretrieve(url, filename)
				return url
			except:
				pass
		f = open(os.path.join(self._home, 'icons', str(feed_id)+'.none'), 'w')
		f.write("")
		f.close()
		return None
			
	def remove_icon(self, feed_id):
		filename = os.path.join(self._home, 'icons', str(feed_id) + '.*')
		result = glob.glob(filename)
		for r in result:
			print "deleting icon:",r
			os.remove(r)
			
	def is_icon_up_to_date(self, feed_id, old_href, feedparser_data):
		url_list = []
		try: url_list.append(feedparser_data['feed']['image']['href'])
		except: pass
		
		try: url_list.append(feedparser_data['feed']['link'] + '/favicon.ico')
		except: pass
		
		if len(url_list) > 0:
			if old_href in url_list:
				filename = os.path.join(self._home, 'icons', str(feed_id) + '.*')
				result = glob.glob(filename)
				if len(result) == 0: #whoops, there's no file there anymore
					return False
				return True
		return False
				
