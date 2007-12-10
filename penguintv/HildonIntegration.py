#
# Contains listeners for various hildon-specific signals like hardware buttons,
# hardware status, etc
#

#hardware buttons
#hardware state
#system exit
#save-on-minimize stuff?
#network status

import logging

class HildonListener:
	def __init__(self, app, h_window):
		self._app = app
		self._h_window = h_window
		
		self._h_window.connect('key_press_event', self.on_hildon_key_press_event)
		
	def on_app_key_press_event(self, widget, event):
		keyname = gtk.gdk.keyval_name(event.keyval)
		
		logging.debug("key: %s" % keyname)
