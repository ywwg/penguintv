# Written by Owen Williams
# see LICENSE for license information

import penguintv
import gtk
import sets
import utils

class EditTagsMultiDialog:
	def __init__(self,xml,app):
		self.xml = xml
		self.app = app
		self.old_tags = []
		self.highlighted_tag = ""
		self.new_set = []
		self.in_common_set = sets.Set()

	def set_feed_list(self, feed_list):
		model = self.feed_list_widget.get_model()
		model.clear()
		for feed in feed_list:
			taglist = self.app.db.get_tags_for_feed(feed[0])
			model.append([feed[0],feed[1], feed[1],self.get_text_tag_list(taglist)])
		self.update_tag_selector()
			
	def update_feed_list(self):
		model = self.feed_list_widget.get_model()
		for feed in model:
			taglist = self.app.db.get_tags_for_feed(feed[0])
			if taglist:
				if self.highlighted_tag is not None:
					if self.highlighted_tag in taglist:
						feed[2] = "<b>"+feed[1]+"</b>"
					else:
						feed[2] = feed[1]
				else:
					feed[2] = feed[1]
			else:
				if self.highlighted_tag is None:
					feed[2] = "<b>"+feed[1]+"</b>"
				else:
					feed[2] = feed[1]
			feed[3] = self.get_text_tag_list(taglist, self.highlighted_tag)
			
	def update_tag_selector(self):
		#make it so after application we keep highlighting.
		model = self.tag_selector_widget.get_model()
		index = self.tag_selector_widget.get_active()
		selected = None
		if index != -1:
			selected = model[index][0]
		model.clear()
		self.tag_selector_widget.append_text(_("None"))
		self.tag_selector_widget.append_text(_("No Tag"))
		i=1
		for tag in self.app.db.get_all_tags():
			self.tag_selector_widget.append_text(tag)
			if tag == selected:
				index = i
			i=i+1
		if index == -1:
			index = 0
		self.tag_selector_widget.set_active(index)
			
	#def find_index_of_item(self, tag):
	#	i=0
	#	model = self.tag_selector_widget.get_model()
	#	for row in model:
	#		print "row: "+str(row[0])+" t: "+str(tag)
	#		if row[0] == tag:
	#			return i
	#		i=i+1
	#	return -1
			
	def on_tag_list_activate(self, event):
		self.apply_tags()
	
	def on_apply_button_clicked(self, event):
		self.apply_tags()
		
	def on_tag_list_changed(self, event):
		#we have what is in common or existing in self.in_common_set -- 
		#we need to now also save the new stuff
		#if they have deleted something, it's going to come back.  too bad
		tags=[]
		for tag in self.tag_list_widget.get_text().split(','):
			strip_tag = tag.strip()
			if strip_tag != '':
				tags.append(strip_tag)
		current_set = sets.Set(tags)
		self.new_set = list(current_set.difference(self.in_common_set))
		removed_set = list(self.in_common_set.difference(current_set))
		if len(self.new_set) > 0 or len(removed_set) > 0:
			self.tags_label_widget.set_text("Tags to apply:")
		else:
			model,rows = self.feed_list_widget.get_selection().get_selected_rows()
			if len(rows) > 1:
				self.tags_label_widget.set_text("Tags in common:")
			else:
				self.tags_label_widget.set_text("Tags:")
				
	def apply_tags(self):
		model,rows = self.feed_list_widget.get_selection().get_selected_rows()
		tags=[]
		for tag in self.tag_list_widget.get_text().split(','):
			tags.append(tag.strip())
			
		for row in rows:
			self.app.apply_tags_to_feed(model[row][0], self.old_tags, tags)
			model[row][3] = self.get_text_tag_list(self.app.db.get_tags_for_feed(model[row][0]))
		self.old_tags = tags
		self.new_set = []
		self.update_tag_selector()
		self.update_feed_list()
	
	def feed_selection_changed(self, selection):
		self.in_common_set = sets.Set()
		model,rows = selection.get_selected_rows()
		
		if len(self.new_set)>0:
			self.tags_label_widget.set_text("Tags to apply:")
		elif len(rows) > 1:
			self.tags_label_widget.set_text("Tags in common:")
		else:
			self.tags_label_widget.set_text("Tags:")
		first=True
		for row in rows:
 			feed_id,title,markuptitle,taglist = model[row]
 			if first:
 				first=False
	 			self.in_common_set = sets.Set(self.app.db.get_tags_for_feed(feed_id))
	 		else:
	 			this_feed_tags = sets.Set(self.app.db.get_tags_for_feed(feed_id))
	 			self.in_common_set = self.in_common_set.intersection(this_feed_tags)
	 	
	 	tag_list = list(self.in_common_set)
	 	tag_list.sort()
	 	self.old_tags = tag_list
		self.tag_list_widget.set_text(self.get_text_tag_list(tag_list+self.new_set))
		
	def on_tag_selector_changed(self, event):
		model = self.tag_selector_widget.get_model()
		selected = self.tag_selector_widget.get_active()
		if selected == 0:
			current_tag = ""
		elif selected == 1:
			current_tag = None
		else:
			current_tag = model[selected][0]
		self.highlighted_tag = current_tag
		self.update_feed_list()
		selection = self.feed_list_widget.get_selection() 
		list_model = self.feed_list_widget.get_model()
		i=0
		for feed in list_model:
			taglist = self.app.db.get_tags_for_feed(feed[0])
			if taglist:
				if self.highlighted_tag is not None:
					if self.highlighted_tag in taglist:
						selection.select_path((i,))
					else:
						selection.unselect_path((i,))
				else:
					selection.unselect_path((i,))
			else:
				if self.highlighted_tag is None:
					selection.select_path((i,))
				else:
					selection.unselect_path((i,))
			i+=1
 			
 	def on_close_clicked(self,event):
 		self.hide()
 		
 	def get_text_tag_list(self, taglist, highlight=None):
 		taglist = utils.uniquer(taglist)
		text = ""
		if taglist:
			if len(taglist)>0:
				for tag in taglist:
					if highlight:
						if tag == highlight:
							text=text+"<b>"+tag+"</b>, "
						else:
							text=text+tag+", "
					else:
						text=text+tag+", "
				text = text[0:-2]
		return text
 				
 	def show(self):
 		self.window = self.xml.get_widget("window_edit_tags_multi")
		for key in dir(self.__class__):
			if key[:3] == 'on_':
				self.xml.signal_connect(key, getattr(self,key))
				
		self.feed_list_widget = self.xml.get_widget("feed_list")
		self.feed_list_model = gtk.ListStore(int,str,str,str) #feed_id, title, markuptitle, tags
		self.feed_list_widget.set_model(self.feed_list_model)		
		
		renderer = gtk.CellRendererText()
		feed_column = gtk.TreeViewColumn('Feeds')
		feed_column.pack_start(renderer, True)
		feed_column.set_attributes(renderer, markup=2)
		self.feed_list_widget.append_column(feed_column)
		
		renderer = gtk.CellRendererText()
		feed_column = gtk.TreeViewColumn('Tags')
		feed_column.pack_start(renderer, True)
		feed_column.set_attributes(renderer, markup=3)
		self.feed_list_widget.append_column(feed_column)
		
		self.feed_list_widget.get_selection().set_mode(gtk.SELECTION_MULTIPLE)
		
		self.tags_label_widget = self.xml.get_widget("tags_label")
		self.tag_list_widget = self.xml.get_widget("tag_list")
		self.tag_selector_widget = self.xml.get_widget("tag_selector")
		tag_selector_model = gtk.ListStore(str)
		self.tag_selector_widget.set_model(tag_selector_model)
			
		self.feed_list_widget.get_selection().connect("changed", self.feed_selection_changed)
		 	
		self.window.resize(500,500)
		self.window.show()
		
	def on_window_edit_tags_multi_destroy_event(self,data1,data2):
		self.hide()
		
	def on_window_edit_tags_multi_delete_event(self, data1,data2):
		return self.window.hide_on_delete()
		
	def hide(self):
		self.window.hide()
