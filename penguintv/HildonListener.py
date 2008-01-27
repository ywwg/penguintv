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

import osso
import conic

class HildonListener:
	def __init__(self, app, h_window, h_context):
		self._app = app
		self._h_window = h_window
		self._h_context = h_context
		
		state = osso.DeviceState(self._h_context)
		state.set_device_state_callback(self._device_state_cb)
		
		con = conic.Connection()
		con.connect('connection-event', self._connection_cb)
		if not con.request_connection(conic.CONNECT_FLAG_NONE):
			logging.debug("error with conic connection thingy")
		
	def _device_state_cb(self, shutdown, save_unsaved_data, memory_low, system_inactivity, message, loop):
		print "Shutdown: ", shutdown
		print "Save unsaved data: ", save_unsaved_data
		print "Memory low: ", memory_low
		print "System Inactivity: ", system_inactivity
		print "Message: ", message
		
	def _connection_cb(self, con, event):
		status = event.get_status()
		
		if status == conic.CONNECTION_CONNECTED:
			logging.debug("CONIC CONNECTED")
			self._app.maybe_change_online_status(True)
		elif status == conic.CONNECTION_DISCONNECTING:
			logging.debug("CONIC DISCONNECTING")
			self._app.maybe_change_online_status(False)
		elif status == conic.CONNECTION_DISCONNECTED:
			logging.debug("CONIC DISCONNECTED")
			self._app.maybe_change_online_status(False)
