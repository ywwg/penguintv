# class template for various html widgets
import threading
import os, os.path
import re
import time

import gobject
import gtk

import PTVhtml
import ThreadPool
import SimpleImageCache

IMG_REGEX = re.compile("<img.*?src=[\",\'](.*?)[\",\'].*?>", re.IGNORECASE|re.DOTALL)

class PTVGtkHtml(PTVhtml.PTVhtml):
	def __init__(self, view, home, share_path):
		PTVhtml.PTVhtml.__init__(self, view, home, share_path)
		self._htmlview = None
		self._document_lock = threading.Lock()
		self._image_cache = SimpleImageCache.SimpleImageCache()
		self._css = ""
		
		self._view = view
		
		f = open(os.path.join(share_path, "gtkhtml.css"))
		for l in f.readlines(): self._css += l
		f.close()
		self._image_pool = ThreadPool.ThreadPool(5, "PlanetView")
		self._dl_total = 0
		self._dl_count = 0
		
	def finish(self):
		self._image_pool.joinAll(False, False)
		del self._image_pool
		
	def is_ajax_ok(self):
		return False
		
	def post_show_init(self, widget):
		import gtkhtml2
		import SimpleImageCache
		import threading
		
		htmlview = gtkhtml2.View()
		self._document = gtkhtml2.Document()
		self._document.connect("link-clicked", self._link_clicked)
		htmlview.connect("on_url", self._on_url)
		self._document.connect("request-url", self._request_url)
		htmlview.get_vadjustment().set_value(0)
		htmlview.get_hadjustment().set_value(0)
		
		self._document.clear()
		htmlview.set_document(self._document)
		self._htmlview = htmlview
		
		widget.set_property("shadow-type",gtk.SHADOW_IN)
		widget.set_hadjustment(self._htmlview.get_hadjustment())
		widget.set_vadjustment(self._htmlview.get_vadjustment())
		widget.add(self._htmlview)
		self._scrolled_window = widget
		
	def build_header(self, html=""):
		header = ["""<html><head>
			    <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
<style type="text/css">
%s
</style>
			    <title>title</title>""" % self._css] 
		header.append(html)
		header.append("""</head>""")
		return "\n".join(header)	
			
	def render(self, html, stream_url="file:///", display_id=None):
		self._document_lock.acquire()
		imgs = IMG_REGEX.findall(html)
		uncached=0
		for url in imgs:
			if not self._image_cache.is_cached(url):
				uncached+=1
				
		if uncached > 0:
			self._document.clear()
			self._document.open_stream("text/html")
			d = { 	"background_color": self._view.get_bg_color(),
					"loading": _("Loading images...")}
			self._document.write_stream("""<html><style type="text/css">
	        body { background-color: %(background_color)s; }</style><body><i>%(loading)s</i></body></html>""" % d) 
			self._document.close_stream()
			self._document_lock.release()
			
			self._dl_count = 0
			self._dl_total = uncached
			
			for url in imgs:
				if not self._image_cache.is_cached(url):
					self._image_pool.queueTask(self._do_download_image, (url, display_id), self._image_dl_cb)
			self._image_pool.queueTask(self._download_done, (display_id, html))
		else:
			self._scrolled_window.get_hadjustment().set_value(0)
			self._scrolled_window.get_vadjustment().set_value(0)
			self._document.clear()
			self._document.open_stream("text/html")
			self._document.write_stream(html)
			self._document.close_stream()
			self._document_lock.release()
			
	def dl_interrupt(self):
		self._image_pool.joinAll(False, False)
		self._dl_count = 0
		self._dl_total = 0
				
	def _do_download_image(self, args):
		url, display_id = args
		self._image_cache.get_image(url)
		#print "do download", display_id
		return display_id
		
	def _image_dl_cb(self, display_id):
		#print "dl_cb", display_id, self._view.get_display_id()
		if display_id == self._view.get_display_id():
			self._dl_count += 1
			
	def _download_done(self, args):
		display_id, html = args
		
		count = 0
		last_count = self._dl_count
		#print "dl_done", display_id, self._view.get_display_id()
		while display_id == self._view.get_display_id() and count < (10 * 2):
			if last_count != self._dl_count:
				#if downloads are still coming in, reset counter
				last_count = self._dl_count
				count = 0
			if self._dl_count >= self._dl_total:
				gobject.idle_add(self._images_loaded, display_id, html)
				return
			count += 1
			time.sleep(0.5)
		gobject.idle_add(self._images_loaded, display_id, html)

		
	def _images_loaded(self, display_id, html):
		#if we're changing, nevermind.
		#also make sure entry is the same and that we shouldn't be blanks
		#print "loaded", display_id, self._view.get_display_id()
		if display_id == self._view.get_display_id():
			va = self._scrolled_window.get_vadjustment()
			ha = self._scrolled_window.get_hadjustment()
			self._document_lock.acquire()
			self._document.clear()
			self._document.open_stream("text/html")
			self._document.write_stream(html)
			self._document.close_stream()
			self._document_lock.release()
		return False
		
	def _request_url(self, document, url, stream):
		try:
			image = self._image_cache.get_image(url)
			stream.write(image)
			stream.close()
		except Exception, ex:
			stream.close()
			
	def _link_clicked(self, document, link):
		link = link.strip()
		self.emit('open-uri', link)
	
	def _on_url(self, view, url):
		if url is None:
			url = ""
		self.emit('link-message', url)
		
