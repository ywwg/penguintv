# Written by Owen Williams
# see LICENSE for license information

import penguintv

class LoginDialog:
	def __init__(self,xml):
		self.xml = xml
		self._dialog = xml.get_widget("dialog_login")
		for key in dir(self.__class__):
			if key[:3] == 'on_':
				self.xml.signal_connect(key, getattr(self,key))
		self._user_widget = self.xml.get_widget("user_widget")
		self._pass_widget = self.xml.get_widget("pass_widget")
		self.username = ""
		self.password = ""
				
	def run(self):
		self._user_widget.grab_focus()
		return self._dialog.run()
		
	def on_dialog_rename_feed_delete_event(self, widget, event):
		return self._dialog.hide_on_delete()
		
	def hide(self):
		self.username = self._user_widget.get_text()
		self.password = self._pass_widget.get_text()
		self._pass_widget.set_text("")
		self._dialog.hide()
		
	#def on_button_ok_clicked(self):
	#	print "called"
	#	self.username = self._user_widget.get_text()
	#	self.password = self._pass_widget.get_text()
	#	
	#def on_user_widget_activate(self):
	#	print "user_act"
	#	self._pass_widget.grab_focus()
	#	
	#def on_pass_widget_activate(self):
	#	print "pass_act"
	#	self.on_button_ok_clicked(event)
