# (C) 2007 Owen Williams
#
# A new, more intuitive tag editor

import penguintv
import gtk
import utils

class TagEditorNG:
	
	FEEDID = 0
	TITLE = 1
	TAGGED = 2
	SEPARATOR = 3
	NEWLY_TOGGLED = 4

	def __init__(self, xml, app):
		self._xml = xml
		self._app = app
		self._current_tag = None
		
		self._app.connect("feed-added", self.__feed_added_cb)
		self._app.connect("feed-removed", self.__feed_removed_cb)
		self._app.connect("tags-changed", self.__tags_changed_cb)
		self._handlers.append((app.disconnect, h_id))
		
	def show(self):
 		self._window = self._xml.get_widget("dialog_tag_editor_ng")
 		self._window.set_transient_for(self._app.main_window.get_parent())
		for key in dir(self.__class__):
			if key[:3] == '_on':
				self._xml.signal_connect(key, getattr(self,key))
				
		self._feeds_widget = self._xml.get_widget("treeview_feeds")
		self._feeds_model = gtk.ListStore(int, str, bool, bool, bool) #feed_id, title, tagged, separator, newly toggled
		self._feeds_widget.set_row_separator_func(lambda m,i:m[i][self.SEPARATOR] == True)
		self._sorted_model = gtk.TreeModelSort(self._feeds_model)
		
		def feed_sort_func(model, i1, i2):
			#use lists to not affect actual values
			r1 = list(model[i1])
			r2 = list(model[i2])
			
			#if either is newly selected, treat as unchecked for sorting
			if r1[self.NEWLY_TOGGLED] == True: r1[self.TAGGED] = not r1[self.TAGGED]
			if r2[self.NEWLY_TOGGLED] == True: r2[self.TAGGED] = not r2[self.TAGGED]
			
			#test separator
			if r1[self.SEPARATOR] == True:
				if r2[self.TAGGED]: return -1
				else: return 1
			if r2[self.SEPARATOR] == True:
				if r1[self.TAGGED]: return 1
				else: return -1

			#test checkboxes
			if r1[self.TAGGED] != r2[self.TAGGED]:
				return r1[self.TAGGED] - r2[self.TAGGED]
			
			#correct for weird bug
			if r1[self.TITLE] is None: r1[self.TITLE] = ""
			if r2[self.TITLE] is None: r2[self.TITLE] = ""
				
			#sort by name
			if r1[self.TITLE].upper() < r2[self.TITLE].upper():
				return 1
			elif r1[self.TITLE].upper() == r2[self.TITLE].upper():
				return 0
			return -1
				
		self._sorted_model.set_sort_func(0, feed_sort_func) 
		self._sorted_model.set_sort_column_id(0, gtk.SORT_DESCENDING)

		self._feeds_widget.set_model(self._sorted_model)		
		
		renderer = gtk.CellRendererToggle()
		feed_column = gtk.TreeViewColumn('')
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
		tags_model = gtk.ListStore(str) #tag
		self._tags_widget.set_model(tags_model)		
		
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
		
	def __feed_added_cb(self, app, a, b):
		self._populate_lists()
		
	def __feed_removed_cb(self, app, a):
		self._populate_lists()
		
	def __tags_changed_cb(self, app, val):
		# if we initiated the change we set val=1
		# the app sets val=0
		if val != 1:
			self._populate_lists()

	def _populate_lists(self):
		self._feeds_model.clear()
		for feed_id, title, url in self._app.db.get_feedlist():
			self._feeds_model.append([feed_id, title, False, False, False])
		self._feeds_model.append([-1, "None", False, True, False])

		model = self._tags_widget.get_model()
		model.clear()
		for tag, favorite in self._app.db.get_all_tags():
			model.append([tag])
			
	def _tags_widget_changed(self, event):
		tags_model = self._tags_widget.get_model()
		selected = self._tags_widget.get_selection().get_selected()
		try:
			self._current_tag = tags_model[selected[1]][0]
			tagged_feeds = self._app.db.get_feeds_for_tag(self._current_tag)
		except:
			self._current_tag = None
			tagged_feeds = []
		
		for row in self._feeds_model:
			#reset "newly selected" feeds
			row[self.NEWLY_TOGGLED] = False
			row[self.TAGGED] = row[self.FEEDID] in tagged_feeds			
			
	def _feed_toggled(self, obj, path):
		if self._current_tag is None:
			return
	
		path = self._sorted_model.convert_path_to_child_path(path)
		row = self._feeds_model[path]

		row[self.TAGGED] = not row[self.TAGGED]
		row[self.NEWLY_TOGGLED] = not row[self.NEWLY_TOGGLED]
		
		if row[self.TAGGED]:
			self._app.db.add_tag_for_feed(row[self.FEEDID], self._current_tag)
			self._app.emit('tags-changed', 1)
		else:
			self._app.db.remove_tag_from_feed(row[self.FEEDID], self._current_tag)
			self._app.emit('tags-changed', 1)
			
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
		#FIXME: do we need to check if the new_name already exists?
		model = self._tags_widget.get_model()
		self._rename_tag(model[path][0], new_text)
			
	def _rename_tag(self, old_name, new_name):
		#FIXME: do we need to check if the new_name already exists?
		self._app.db.rename_tag(old_name, new_name)
		self._app.emit('tags-changed', 1)
		
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
			self._app.db.remove_tag(self._current_tag)
			self._app.emit('tags-changed', 1)
			
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
