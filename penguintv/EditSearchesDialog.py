# Written by Owen Williams
# see LICENSE for license information

import penguintv
from ptvDB import TagAlreadyExists
import gtk
import sets
import utils

class EditSearchesDialog:
	def __init__(self,xml,app):
		self._xml = xml
		self._app = app
		
	def on_remove_button_clicked(self, event):
		selection = self._saved_search_list_widget.get_selection()
		model, iter = selection.get_selected()
		
		if iter is not None:
			saved_item = model[iter]
			i=-1
			for item in model:
				i+=1
				if item[0] == saved_item[0]:
					break
			saved_pos = i
			
		self._app.remove_search_tag(model[iter][0])
		
		self._populate_searches()
					
		if iter is not None:
			if saved_pos <= len(model):
				selection = self._saved_search_list_widget.get_selection()
				selection.select_path((saved_pos,))
				return
		
	def on_add_button_clicked(self, event):
		self._add_search()
	
	def on_tag_name_entry_activate(self, event):
		self._app.change_search_tag()
		
	def on_query_entry_activate(self, event):
		self._app.change_search_tag()
		
	def on_tag_edit_done(self, renderer, path, new_text):
		model = self._saved_search_list_widget.get_model()
		self._app.change_search_tag(model[path][0], new_tag=new_text)
		model[path][0] = new_text
		self._saved_search_list_widget.grab_focus()
		self._saved_search_list_widget.set_cursor(len(model)-1, self._query_column, True)
		
	def on_query_edit_done(self, renderer, path, new_text):
		model = self._saved_search_list_widget.get_model()
		self._app.change_search_tag(model[path][0], new_query=new_text)
		model[path][1] = new_text
				
	def on_close_button_clicked(self,event):
 		self.hide()
 		
 	def on_window_edit_search_tags_destroy_event(self,data1,data2):
		self.hide()
		
	def on_window_edit_search_tags_delete_event(self, data1,data2):
		return self._window.hide_on_delete()
		
	def hide(self):
		self._window.hide()
 		
 	def show(self):
 		self._window = self._xml.get_widget("window_edit_search_tags")
		for key in dir(self.__class__):
			if key[:3] == 'on_':
				self._xml.signal_connect(key, getattr(self,key))
				
		self._saved_search_list_widget = self._xml.get_widget("saved_search_list")
		model = gtk.ListStore(str, str) #tag name, query
		self._saved_search_list_widget.set_model(model)		
		
		renderer = gtk.CellRendererText()
		renderer.set_property("editable",True)
		renderer.connect("edited", self.on_tag_edit_done)
		self._tag_column = gtk.TreeViewColumn('Search Tag Name')
		self._tag_column.pack_start(renderer, True)
		self._tag_column.set_attributes(renderer, markup=0)
		self._saved_search_list_widget.append_column(self._tag_column)
		
		renderer = gtk.CellRendererText()
		renderer.set_property("editable",True)
		renderer.connect("edited", self.on_query_edit_done)
		self._query_column = gtk.TreeViewColumn('Query')
		self._query_column.pack_start(renderer, True)
		self._query_column.set_attributes(renderer, markup=1)
		self._saved_search_list_widget.append_column(self._query_column)
		
		self._window.resize(500,500)
		self._window.show()
		self._populate_searches()
		
	def apply_tags(self):
		pass
		
	def _populate_searches(self):
		model = self._saved_search_list_widget.get_model()
		model.clear()
		searches = self._app.db.get_search_tags()
		if searches:
			for search in searches:
				model.append([search[0],search[1]])
				
	def _add_search(self):
		current_query=_("New Query")
		current_tag=_("New Tag")

		def try_add_tag(basename, query, i=0):
			try:
				if i>0:
					#self._app.db.add_search_tag(query, basename+" "+str(i))
					self._app.add_search_tag(query, basename+" "+str(i))
					return basename+" "+str(i)
				#self._app.db.add_search_tag(query, basename)
				self._app.add_search_tag(query, basename+" "+str(i))
				return basename
			except TagAlreadyExists, e:
				return try_add_tag(basename, query, i+1)
				
		current_tag = try_add_tag(current_tag, current_query)
		model = self._saved_search_list_widget.get_model()
		model.append([current_tag,current_query])
		self._saved_search_list_widget.set_cursor(len(model)-1, self._tag_column, True)
