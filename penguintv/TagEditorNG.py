# (C) 2007 Owen Williams
#
# A new, more intuitive tag editor

import penguintv
import gtk
import utils

class TagEditorNG:
	def __init__(self, xml, app):
		self._xml = xml
		self._app = app
		self._db = self._app.db
		self._current_tag = None
		
		self._app.connect("feed-added", self._populate_lists)
		self._app.connect("feed-removed", self._populate_lists)
		
	def show(self):
 		self._window = self._xml.get_widget("dialog_tag_editor_ng")
		for key in dir(self.__class__):
			if key[:3] == '_on':
				self._xml.signal_connect(key, getattr(self,key))
				
		self._feeds_widget = self._xml.get_widget("treeview_feeds")
		self._feeds_model = gtk.ListStore(int, str, bool) #feed_id, title, tagged
		self._feeds_widget.set_model(self._feeds_model)		
		
		renderer = gtk.CellRendererToggle()
		feed_column = gtk.TreeViewColumn('Tagged')
		feed_column.pack_start(renderer, True)
		self._feeds_widget.append_column(feed_column)
		feed_column.set_attributes(renderer, active=2)
		renderer.connect('toggled', self._feed_toggled)
		
		renderer = gtk.CellRendererText()
		feed_column = gtk.TreeViewColumn('Feeds')
		feed_column.pack_start(renderer, True)
		feed_column.set_attributes(renderer, markup=1)
		self._feeds_widget.append_column(feed_column)
		
		self._tags_widget = self._xml.get_widget("treeview_tags")
		self._tags_model = gtk.ListStore(str) #tag
		self._tags_widget.set_model(self._tags_model)		
		
		renderer = gtk.CellRendererText()
		renderer.set_property('editable', True)
		renderer.connect('edited', self._tag_name_edited)
		tag_column = gtk.TreeViewColumn('Tags')
		tag_column.pack_start(renderer, True)
		tag_column.set_attributes(renderer, markup=0)
		
		
		self._tags_widget.append_column(tag_column)
		
		self._tags_widget.get_selection().connect('changed', self._tags_widget_changed)
		
		pane = self._xml.get_widget("hpaned")
		pane.set_position(200)
		
		self._window.resize(500,600)
		self._window.show()
		
		self._populate_lists()

	def _populate_lists(self):
		model = self._feeds_widget.get_model()
		model.clear()
		for feed_id, title in self._db.get_feedlist():
			model.append([feed_id, title, False])

		model = self._tags_widget.get_model()
		model.clear()
		for tag, favorite in self._db.get_all_tags():
			model.append([tag])
			
	def _tags_widget_changed(self, event):
		tags_model = self._tags_widget.get_model()
		selected = self._tags_widget.get_selection().get_selected()
		try:
			self._current_tag = tags_model[selected[1]][0]
			tagged_feeds = self._db.get_feeds_for_tag(self._current_tag)
		except:
			self._current_tag = None
			tagged_feeds = []
		
		feed_model = self._feeds_widget.get_model()
		for row in feed_model:
			row[2] = row[0] in tagged_feeds			
			
	def _feed_toggled(self, obj, path):
		model = self._feeds_widget.get_model()
		row = model[path]
		row[2] = not row[2]
		if row[2]:
			self._db.add_tag_for_feed(row[0], self._current_tag)
		else:
			self._db.remove_tag_from_feed(row[0], self._current_tag)
			
	def _on_button_rename_clicked(self, event):
		if self._current_tag is None:
			return
	
		# pop up a dialog to rename the current tag
		dialog = gtk.Dialog(title=_("Rename Tag"), parent=None, flags=gtk.DIALOG_MODAL, buttons=(gtk.STOCK_CANCEL, gtk.RESPONSE_REJECT, gtk.STOCK_OK, gtk.RESPONSE_ACCEPT))

		label = gtk.Label(_("Please enter a new name for this tag"))
		dialog.vbox.pack_start(label, True, True, 0)
		
		entry = gtk.Entry()
		dialog.vbox.pack_start(entry)
		
		dialog.show_all()
		response = dialog.run()
		dialog.hide()
		del dialog
		if response == gtk.RESPONSE_ACCEPT:	
			# rename this item
			new_name = entry.get_text()
			self._rename_tag(self._current_tag, new_name)
			
	def _tag_name_edited(self, renderer, path, new_text):
		model = self._tags_widget.get_model()
		self._rename_tag(model[path][0], new_text)
			
	def _rename_tag(self, old_name, new_name):
		self._db.rename_tag(old_name, new_name)
		
		# resort
		selection = self._tags_widget.get_selection()
		model, old_iter = selection.get_selected()	
		model.remove(old_iter)
		
		self._current_tag = new_name
		
		new_index = -1
		i = -1
		for row in model:
			i += 1
			if new_name.upper() < row[0].upper():
				new_index = i
				break
		if new_index == -1:
			new_index = len(model) - 1
		model.insert(new_index,[new_name])
		
		new_iter = model.get_iter((new_index,))
		self._tags_widget.scroll_to_cell((new_index,))
		selection.select_path((new_index,))

	def _on_button_add_clicked(self, event):
		# pop up a dialog to ask for a name, and add it... how to deal with
		# a tag with no associated feed????  ... I don't think it even matters
		# because the tag will be "created" as soon as we check a box
		
		# pop up a dialog to rename the current tag
		dialog = gtk.Dialog(title=_("Rename Tag"), parent=None, flags=gtk.DIALOG_MODAL, buttons=(gtk.STOCK_CANCEL, gtk.RESPONSE_REJECT, gtk.STOCK_OK, gtk.RESPONSE_ACCEPT))

		label = gtk.Label(_("Please enter a name for this new tag:"))
		dialog.vbox.pack_start(label, True, True, 0)
		
		entry = gtk.Entry()
		dialog.vbox.pack_start(entry)
		
		dialog.show_all()
		response = dialog.run()
		dialog.hide()
		del dialog
		if response == gtk.RESPONSE_ACCEPT:
			# rename this item
			tag_name = entry.get_text()
			
			# add tag to our list
			model = self._tags_widget.get_model()
			selection = self._tags_widget.get_selection()
			
			self._current_tag = tag_name
			
			new_index = -1
			i = -1
			for row in model:
				i += 1
				if tag_name.upper() < row[0].upper():
					new_index = i
					break
			if new_index == -1:
				new_index = len(model) - 1
			model.insert(new_index,[tag_name])
			
			# select it
			new_iter = model.get_iter((new_index,))
			self._tags_widget.scroll_to_cell((new_index,))
			selection.select_iter(new_iter)
		
	def _on_button_remove_clicked(self, event):
		if self._current_tag is None:
			return 
	
		dialog = gtk.Dialog(title=_("Really Delete Tag?"), parent=None, flags=gtk.DIALOG_MODAL, buttons=(gtk.STOCK_CANCEL, gtk.RESPONSE_REJECT, gtk.STOCK_OK, gtk.RESPONSE_ACCEPT))
		label = gtk.Label(_("Are you sure you want to remove this tag from all feeds?"))
		dialog.vbox.pack_start(label, True, True, 0)
		label.show()
		response = dialog.run()
		dialog.hide()
		del dialog
		if response == gtk.RESPONSE_ACCEPT:	
			#remove from db	
			self._db.remove_tag(self._current_tag)
			
			#remove tag from our list
			selection = self._tags_widget.get_selection()
			model, old_iter = selection.get_selected()	
			model.remove(old_iter)
			
			self._current_tag = None
			
			#select nothing
			self._tags_widget.scroll_to_cell((0,))
			selection.unselect_all()
		
 	def _on_button_close_clicked(self, event):
 		self.hide()
 		
	def on_dialog_tag_editor_ng_destroy_event(self, data1, data2):
		self.hide()
		
	def on_dialog_tag_editor_ng_delete_event(self, data1, data2):
		return self._window.hide_on_delete()
		
	def hide(self):
		self._window.hide()
