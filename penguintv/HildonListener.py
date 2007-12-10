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

import gtk

class HildonListener:
	def __init__(self, app, h_window):
		self._app = app
		self._h_window = h_window
