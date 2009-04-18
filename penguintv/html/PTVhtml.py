# class template for various html widgets
import gobject

class PTVhtml(gobject.GObject):
	__gsignals__ = {
       	'link-message': (gobject.SIGNAL_RUN_LAST, 
                           gobject.TYPE_NONE, 
                           ([gobject.TYPE_STRING])),
		'open-uri': (gobject.SIGNAL_RUN_LAST, 
                           gobject.TYPE_NONE, 
                           ([gobject.TYPE_STRING]))
    }	   

	def __init__(self, view, home, share_path):
		gobject.GObject.__init__(self)
		
	def finish(self):
		assert False
		
	def is_ajax_ok(self):
		"""does the widget support ajax"""
		assert False
		
	def post_show_init(self, widget):
		"""widget must be a gtkscrolledwindow.  HTML widget will install itself
		in the scrolled window and show itself"""
		assert False
	
	def build_header(self, html):
		"""build the html header needed (fonts, css, etc)
		html is a string to be appended to the header before closing tags"""
		assert False
		
	def render(self, html, stream_url="file:///", image_id=None):
		"""html is a string of html
		stream_url is the 'root' path or whatever the terminology is
		display_id is an object that an image downloader will compare against
			to determine if it should continue displaying the image"""
		assert False
		
	def dl_interrupt(self):
		"""stop downloading images (if applicable)"""
		assert False
		
	
