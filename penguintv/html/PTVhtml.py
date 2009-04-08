# class template for various html widgets
import gobject

class PTVhtml(gobject.GObject):
	__gsignals__ = {
       	'link-message': (gobject.SIGNAL_RUN_FIRST, 
                           gobject.TYPE_NONE, 
                           ([gobject.TYPE_STRING])),
		'open-uri': (gobject.SIGNAL_RUN_FIRST, 
                           gobject.TYPE_NONE, 
                           ([gobject.TYPE_STRING]))
    }	   

	def __init__(self, view, home, share_path):
		gobject.GObject.__init__(self)
		
	def finish(self):
		assert False
		
	def is_ajax_ok(self):
		assert False
		
	def post_show_init(self):
		assert False
	
	def get_widget(self):
		assert False
	
	def build_header(self):
		assert False
		
	def render(self, html, stream_url="file:///", image_id=None):
		assert False
		
	def dl_interrupt(self):
		assert False
		
	
