import ptv_sync
import gconf
import gtk.glade
import gobject

import os, os.path

class SynchronizeDialog:
	def __init__(self, gladefile):
		self._conf = gconf.client_get_default()
		self._xml = gtk.glade.XML(gladefile, 'synchronize_window','penguintv')
		self._dialog = self._xml.get_widget("synchronize_window")
		self._preview_dialog = self._xml.get_widget("sync_preview_window")
		for key in dir(self.__class__):
			if key[:3] == 'on_':
				self._xml.signal_connect(key, getattr(self,key))
				
		self._audio_check = self._xml.get_widget("audio_check")
		self._delete_check = self._xml.get_widget("delete_check")
		self._destination_entry = self._xml.get_widget("dest_entry")
		
		self._conf.add_dir('/apps/penguintv',gconf.CLIENT_PRELOAD_NONE)
		self._conf.notify_add('/apps/penguintv/sync_delete',self.set_sync_delete)
		self._conf.notify_add('/apps/penguintv/sync_audio_only',self.set_audio_only)
		self._conf.notify_add('/apps/penguintv/sync_dest_dir',self.set_dest_dir)
		
		self._progress_dialog = SynchronizeDialog.SyncProgress(gtk.glade.XML(gladefile, 'sync_progress_window','penguintv'), self._cancel_cb)
		self._preview_dialog = SynchronizeDialog.SyncPreview(gtk.glade.XML(gladefile, 'sync_preview_window','penguintv'), self._cancel_cb, self._sync_cb)
		
	def Show(self):
		try: self._delete_check.set_active(self._conf.get_bool('/apps/penguintv/sync_delete'))
		except: self._delete_check.set_active(False)
			
		try: self._audio_check.set_active(self._conf.get_bool('/apps/penguintv/sync_audio_only'))
		except: self._audio_check.set_active(False)
		
		try: self._dest_dir = self._conf.get_string('/apps/penguintv/sync_dest_dir')
		except: self._dest_dir = ""
		if self._dest_dir is None:
			self._dest_dir = ""
		self._destination_entry.set_text(self._dest_dir)
		self._cancel = False

		self._dialog.show()
				
	def run(self):
		self._destination_entry.grab_focus()
		return self._dialog.run()
		
	def check_dest_dir(self):
		self._dest_dir = self._destination_entry.get_text()
		#check to see that it exists and is a dir and is writable by us....
		try:
			stat = os.stat(self._dest_dir)
			if not os.path.isdir(self._dest_dir):
				return False
				
			self._conf.set_string('/apps/penguintv/sync_dest_dir',self._dest_dir)
			return True
		except:
			return False
		
	def _cancel_cb(self):
		self._cancel = True
		self._progress_dialog.hide()
		self._preview_dialog.hide()
		
	def _sync_cb(self):
		self._preview_dialog.hide()
		self.on_sync_button_clicked(None)
		
	def on_browse_button_clicked(self, event):
		pass
	
	def on_delete_check_toggled(self, event):
		self._conf.set_bool('/apps/penguintv/sync_delete',self._delete_check.get_active())
		
	def on_audio_check_toggled(self, event):
		self._conf.set_bool('/apps/penguintv/sync_audio_only',self._audio_check.get_active())
	
	def on_sync_button_clicked(self, event):
		if not self.check_dest_dir():
			dialog = gtk.Dialog(title=_("Destination Error"), parent=None, flags=gtk.DIALOG_MODAL, buttons=(gtk.STOCK_OK, gtk.RESPONSE_ACCEPT))
			label = gtk.Label(_("The destination you have selected is not valid.  \nPlease select another destination and try again."))
			dialog.vbox.pack_start(label, True, True, 0)
			label.show()
			response = dialog.run()
			dialog.hide()
			del dialog
			return
			
		sync = ptv_sync.ptv_sync(self._dest_dir, self._delete_check.get_active(), self._audio_check.get_active())
		self._progress_dialog.progress_bar.set_fraction(0)
		self._progress_dialog.progress_label.set_text("")
		self._progress_dialog.Show()
		self._dialog.hide()
		
		def _sync_gen():
			for event in sync.sync_gen():
				if not self._cancel:
					if event[1] == -1:
						self._progress_dialog.progress_bar.pulse()
					else:
						self._progress_dialog.progress_bar.set_fraction(float(event[0])/float(event[1]))
					self._progress_dialog.progress_label.set_markup("<i>"+event[2]+"</i>")
				else:
					sync.interrupt()
				#else: let the cancel run its course
				#	self._dialog.hide()
				#	self._cancel = False
				#	break
				yield True
			if self._cancel:
				self._dialog.hide()
			self._cancel = False
			self._progress_dialog.hide()
			#dialog = gtk.Dialog(title=_("Copying Complete"), parent=None, flags=gtk.DIALOG_MODAL, buttons=(gtk.STOCK_OK, gtk.RESPONSE_ACCEPT))
			#label = gtk.Label(_("PenguinTV has finished synchronizing media."))
			#dialog.vbox.pack_start(label, True, True, 0)
			#label.show()
			#response = dialog.run()
			#dialog.hide()
			#del dialog
			yield False
			
		gobject.idle_add(_sync_gen().next)
			
	def on_preview_button_clicked(self, event):
		if not self.check_dest_dir():
			dialog = gtk.Dialog(title=_("Destination Error"), parent=None, flags=gtk.DIALOG_MODAL, buttons=(gtk.STOCK_OK, gtk.RESPONSE_ACCEPT))
			label = gtk.Label(_("The destination you have selected is not valid.  Please select another destination and try again."))
			dialog.vbox.pack_start(label, True, True, 0)
			label.show()
			response = dialog.run()
			dialog.hide()
			del dialog
			return
		sync = ptv_sync.ptv_sync(self._dest_dir, self._delete_check.get_active(), self._audio_check.get_active(), True)
		
		self._preview_dialog.buff.set_text("")
		self._preview_dialog.Show()
		self._dialog.hide()

		def _sync_gen():
			text = ""
			last_message = ""
			for event in sync.sync_gen():
				if not self._cancel:
					#text+="\n"+event[2]
					#self._preview_dialog.buff.set_text(text)
					if last_message != event[2]:
						self._preview_dialog.buff.insert_at_cursor(event[2]+"\n")
					last_message = event[2]
				else:
					sync.interrupt()
				#else:... just yield, let the generator run its course
				yield True
			if self._cancel:
				self._dialog.hide()
			self._cancel = False
			yield False
		gobject.idle_add(_sync_gen().next)			
			
	def on_cancel_button_clicked(self, event):
		self.hide()
	
	def on_synchronize_window_delete_event(self, widget, event):
		return self._dialog.hide_on_delete()
		
	def hide(self):
		self._dialog.hide()
		
	def set_sync_delete(self, client, *args, **kwargs):
		self._delete_check.set_active(self._conf.get_bool('/apps/penguintv/sync_delete'))
		
	def set_audio_only(self, client, *args, **kwargs):
		self._audio_check.set_active(self._conf.get_bool('/apps/penguintv/sync_audio_only'))
		
	def set_dest_dir(self, client, *args, **kwargs):
		self._dest_dir = self._conf.get_string('/apps/penguintv/sync_dest_dir')
		self._destination_entry.set_text(self._dest_dir)
		
	class SyncProgress:
		def __init__(self, xml, cancel_cb):
			self._dialog = xml.get_widget('sync_progress_window')
			self.progress_bar = xml.get_widget('sync_progressbar')
			self.progress_bar.set_pulse_step(.05)
			self.progress_label = xml.get_widget('progress_info_label')
			self._cancel_cb = cancel_cb
			for key in dir(self.__class__):
				if key[:3] == 'on_':
					xml.signal_connect(key, getattr(self,key))
					
		def Show(self):
			self._dialog.show_all()
			
		def hide(self):
			self._dialog.hide()
			
		def on_sync_progress_window_delete_event(self, widget, event):
			return self._dialog.hide_on_delete()
		
		def on_cancel_button_clicked(self, event):
			self._cancel_cb()
			self.hide()
	
	class SyncPreview:
		def __init__(self, xml, cancel_cb, sync_cb):
			self._dialog = xml.get_widget('sync_preview_window')
			self._cancel_cb = cancel_cb
			self._sync_cb = sync_cb
			self.buff = gtk.TextBuffer()
			self._sync_textview = xml.get_widget('sync_textview')
			self._sync_textview.set_buffer(self.buff)
			
			for key in dir(self.__class__):
				if key[:3] == 'on_':
					xml.signal_connect(key, getattr(self,key))
			
		def Show(self):
			self._dialog.show_all()
			
		def hide(self):
			self._dialog.hide()
			
		def on_sync_preview_window_delete_event(self, widget, event):
			return self._dialog.hide_on_delete()
			
		def on_sync_button_clicked(self, event):
			self._sync_cb()
			self.hide()
			
		def on_cancel_button_clicked(self, event):
			print "cancel clicked"
			self._cancel_cb()
			self.hide()
