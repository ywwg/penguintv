# Written by Owen Williams
# see LICENSE for license information

import penguintv
from ptvDB import TagAlreadyExists
import gtk
import sets
import utils

class EditSearchesDialog:
	def __init__(self,xml,app):
		self.xml = xml
		self.app = app
		
	def on_remove_button_clicked(self, event):
		selection = self.saved_search_list_widget.get_selection()
		model, iter = selection.get_selected()
		self.app.db.remove_tag(model[iter][0])
		if iter is not None:
			saved_item = model[iter]
			i=-1
			for item in model:
				i+=1
				if item[0] == saved_item[0]:
					break
			saved_pos = i
		self.populate_searches()
		while gtk.events_pending():
			gtk.main_iteration()
		self.app.main_window.update_filters()			
		if iter is not None:
			if saved_pos <= len(model):
				selection = self.saved_search_list_widget.get_selection()
				selection.select_path((saved_pos,))
				return
		
	def on_add_button_clicked(self, event):
		self.add_search()
	
	def on_tag_name_entry_activate(self, event):
		self.save_search()
		
	def on_query_entry_activate(self, event):
		self.save_search()
		
	def on_tag_edit_done(self, renderer, path, new_text):
		model = self.saved_search_list_widget.get_model()
		self.save_search(model[path][0], new_tag=new_text)
		model[path][0] = new_text
		self.saved_search_list_widget.grab_focus()
		self.saved_search_list_widget.set_cursor(len(model)-1, self.query_column, True)
		
	def on_query_edit_done(self, renderer, path, new_text):
		model = self.saved_search_list_widget.get_model()
		self.save_search(model[path][0], new_query=new_text)
		model[path][1] = new_text
				
	def on_close_button_clicked(self,event):
 		self.hide()
 		
 	def on_window_edit_search_tags_destroy_event(self,data1,data2):
		self.hide()
		
	def on_window_edit_search_tags_delete_event(self, data1,data2):
		return self.window.hide_on_delete()
		
	def hide(self):
		self.window.hide()
 		
 	def show(self):
 		self.window = self.xml.get_widget("window_edit_search_tags")
		for key in dir(self.__class__):
			if key[:3] == 'on_':
				self.xml.signal_connect(key, getattr(self,key))
				
		self.saved_search_list_widget = self.xml.get_widget("saved_search_list")
		model = gtk.ListStore(str, str) #tag name, query
		self.saved_search_list_widget.set_model(model)		
		
		renderer = gtk.CellRendererText()
		renderer.set_property("editable",True)
		renderer.connect("edited", self.on_tag_edit_done)
		self.tag_column = gtk.TreeViewColumn('Search Tag Name')
		self.tag_column.pack_start(renderer, True)
		self.tag_column.set_attributes(renderer, markup=0)
		self.saved_search_list_widget.append_column(self.tag_column)
		
		renderer = gtk.CellRendererText()
		renderer.set_property("editable",True)
		renderer.connect("edited", self.on_query_edit_done)
		self.query_column = gtk.TreeViewColumn('Query')
		self.query_column.pack_start(renderer, True)
		self.query_column.set_attributes(renderer, markup=1)
		self.saved_search_list_widget.append_column(self.query_column)
		
		self.window.resize(500,500)
		self.window.show()
		self.populate_searches()
		
	def apply_tags(self):
		pass
		
	def populate_searches(self):
		model = self.saved_search_list_widget.get_model()
		model.clear()
		searches = self.app.db.get_search_tags()
		if searches:
			for search in searches:
				model.append([search[0],search[1]])
			
	def save_search(self, current_tag, new_tag=None, new_query=None):
		if new_tag is not None:
			self.app.db.rename_tag(current_tag, new_tag)
			
		if new_query is not None:
			self.app.db.change_query_for_tag(current_tag, new_query)
		self.app.main_window.update_filters()
		
	def add_search(self):
		current_query=_("New Query")
		current_tag=_("New Tag")

		def try_add_tag(basename, query, i=0):
			try:
				if i>0:
					self.app.db.add_search_tag(query, basename+" "+str(i))
					return basename+" "+str(i)
				self.app.db.add_search_tag(query, basename)
				return basename
			except TagAlreadyExists, e:
				return try_add_tag(basename, query, i+1)
				
		current_tag = try_add_tag(current_tag, current_query)
		model = self.saved_search_list_widget.get_model()
		model.append([current_tag,current_query])
		self.saved_search_list_widget.set_cursor(len(model)-1, self.tag_column, True)
