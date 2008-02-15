#thanks to http://www.daa.com.au/pipermail/pygtk/2003-November/006304.html
#for the reordering code

import gtk
import pango
from ptvDB import T_BUILTIN

import utils

F_NAME     = 0
F_DISPLAY  = 1
F_INDEX    = 2
F_SEP      = 3

class FilterSelectorDialog(gtk.Window):
	def __init__(self, xml, main_window):
		gtk.Window.__init__(self)
		self._xml = xml
		self._main_window = main_window
		
		#self._widget = self._xml.get_widget('dialog_tag_favorites')
		contents = xml.get_widget("dialog-vbox3")
		p = contents.get_parent()
		contents.reparent(self)
		gtk.Window.set_title(self, p.get_title())
		del p
		
		self._pane = self._xml.get_widget('hpaned')
		
		self._favorites_old_order = []
		self._favorites_treeview = self._xml.get_widget('favorites_treeview')
		self._favorites_model = gtk.ListStore(str, #name of filter
											   str, #text to display
											   int, #original id
											   bool) #separator
													 		
		self._favorites_treeview.set_model(self._favorites_model)

		column = gtk.TreeViewColumn(_('Favorites'))
		renderer = gtk.CellRendererText()
		column.pack_start(renderer)
		column.set_attributes(renderer, text=F_DISPLAY)
		column.set_alignment(0.5)
		self._favorites_treeview.append_column(column)
		
		self._all_tags_model = gtk.ListStore(str, str, int, bool) #same as above
		self._all_tags_treeview = self._xml.get_widget('all_tags_treeview')
		self._all_tags_treeview.set_model(self._all_tags_model)
		self._all_tags_treeview.set_row_separator_func(lambda model,iter:model[iter][F_SEP]==True)
		
		column = gtk.TreeViewColumn(_('All Tags'))
		renderer = gtk.CellRendererText()
		column.pack_start(renderer)
		column.set_attributes(renderer, text=F_DISPLAY)
		column.set_alignment(0.5)
		self._all_tags_treeview.append_column(column)
		
		self._TARGET_TYPE_INTEGER = 80
		self._TARGET_TYPE_REORDER = 81
		drop_types = [ ('reorder',gtk.TARGET_SAME_WIDGET,self._TARGET_TYPE_REORDER),
					   ('integer',gtk.TARGET_SAME_APP,self._TARGET_TYPE_INTEGER)]
		#for removing items from favorites and reordering
		self._favorites_treeview.enable_model_drag_source(gtk.gdk.BUTTON1_MASK, drop_types, gtk.gdk.ACTION_MOVE)
		self._all_tags_treeview.drag_dest_set(gtk.DEST_DEFAULT_ALL, drop_types, gtk.gdk.ACTION_MOVE)
		
		#copying items to favorites
		self._favorites_treeview.enable_model_drag_dest(drop_types, gtk.gdk.ACTION_COPY)
		self._all_tags_treeview.drag_source_set(gtk.gdk.BUTTON1_MASK, drop_types, gtk.gdk.ACTION_COPY)
		
		self._dragging = False
		
		for key in dir(self.__class__): #python insaneness
			if key[:3] == '_on':
				self._xml.signal_connect(key, getattr(self, key))
				
		self._pane_position = 0
		
		if utils.RUNNING_HILDON:
			self._hildon_inited = False
		
	def set_taglists(self, all_tags, favorite_tags):
		self._all_tags_model.clear()
		self._favorites_model.clear()
		
		self._favorites_old_order = []
		
		last_type = all_tags[0][3]
		i=-1
		for favorite, name,display,f_type in all_tags:
			i+=1
			if f_type != T_BUILTIN:
				if f_type != last_type:
					last_type = f_type
					self._all_tags_model.append(['---','---', -1, True])
				self._all_tags_model.append([name, display, i, False])
				if favorite > 0:
					self._favorites_old_order.append([favorite, name, display, i])
				
		self._favorites_old_order.sort()
		for fav, name, display, index in self._favorites_old_order:
			self._favorites_model.append([name, display, index, False])
		
	def is_visible(self):
		return self.get_property('visible')
		
	def Show(self):
		if utils.RUNNING_HILDON:
			if not self._hildon_inited:
				#put in a scrolled viewport so the user can see all the prefs
				parent = self._xml.get_widget('container')
				contents = self._xml.get_widget('contents')
				scrolled = gtk.ScrolledWindow()
				scrolled.set_size_request(650, 200)
				scrolled.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
				viewport = gtk.Viewport()
				contents.reparent(viewport)
				scrolled.add(viewport)
				parent.add(scrolled)
				self._hildon_inited = True
			self._all_tags_treeview.set_property('height-request', 150)
	
		context = self.create_pango_context()
		style = self.get_style().copy()
		font_desc = style.font_desc
		metrics = context.get_metrics(font_desc, None)
		char_width = metrics.get_approximate_char_width()
		
		widest_left = 0
		widest_right = 0
		
		for row in self._all_tags_model:
			width = len(row[F_DISPLAY])
			if width > widest_right:
				widest_right = width
				
		for row in self._favorites_model:
			width = len(row[F_DISPLAY])
			if width > widest_left:
				widest_left = width
		
		self._pane_position = pango.PIXELS((widest_left+10)*char_width)
		self._window_width  = pango.PIXELS((widest_left+widest_right+10)*char_width)+100
		
		self.resize(self._window_width,1)
		self._pane.set_position(self._pane_position)
		self._favorites_treeview.columns_autosize()
		self._all_tags_treeview.columns_autosize()
		
		self.set_transient_for(self._main_window.get_parent())
		
		self.show_all()
		
		if utils.RUNNING_HILDON:
			self._xml.get_widget('info_icon').hide()
			self._pane_position = 250
			self._pane.set_position(self._pane_position)
		
	def Hide(self):
		self._do_unselect()
		self.hide()
		
	def _on_apply_clicked(self, button):
		new_order = [r[0] for r in self._favorites_model]
		old_order = [r[1] for r in self._favorites_old_order]
		if old_order != new_order:
			self._main_window.set_tag_favorites(new_order)
		self.destroy()
		
	def _on_close_clicked(self, button):
		#self.Hide()
		self.destroy()
		
	#def _on_dialog_tag_favorites_delete_event(self, widget, event):
	#	return widget.hide_on_delete()
		
	def _on_drag_data_get(self, treeview, drag_context, selection_data, info, time):
		selection = treeview.get_selection()
		model, iter = selection.get_selected()
		path = model.get_path(iter)
		selection_data.set(selection_data.target, 8, str(path[0]))
		
	def _on_all_tags_drag_data_received(self, treeview, context, x, y, selection, targetType, time):
		treeview.emit_stop_by_name('drag-data-received')
		if targetType == self._TARGET_TYPE_INTEGER:
			tag_index = ""
			for c in selection.data:
				if c != "\0":  #for some reason ever other character is a null.  what gives?
					tag_index = tag_index+c
			index = int(tag_index)
			target_iter = self._favorites_model.get_iter((index,))
			self._favorites_model.remove(target_iter)
		self._on_drag_end(None, None)
		
	def _on_favorites_drag_data_received(self, treeview, context, x, y, selection, targetType, time):
		treeview.emit_stop_by_name('drag-data-received')
		if targetType == self._TARGET_TYPE_INTEGER:
			tag_index = ""
			for c in selection.data:
				if c != "\0":  #for some reason ever other character is a null.  what gives?
					tag_index = tag_index+c
			index = int(tag_index)
			source_row = self._all_tags_model[index]
			for row in self._favorites_model:
				if source_row[F_NAME] == row[F_NAME]:
					return
			new_row = [source_row[F_NAME],source_row[F_DISPLAY],index, False]
			try:
				path, pos = treeview.get_dest_row_at_pos(x, y)
				dest_iter = self._favorites_model.get_iter(path)
				self.iterCopy(self._favorites_model, dest_iter, new_row, pos)
			except:
				self._favorites_model.append(new_row)
		if targetType == self._TARGET_TYPE_REORDER:
			model, iter_to_copy = treeview.get_selection().get_selected()
			row = list(model[iter_to_copy])
			try:
				path, pos = treeview.get_dest_row_at_pos(x, y)
				target_iter = model.get_iter(path)
				
				if self.checkSanity(model, iter_to_copy, target_iter):
					self.iterCopy(model, target_iter, row, pos)
					context.finish(True, True, time)
				else:
					context.finish(False, False, time)
			except:
				model.append(row)
				context.finish(True, True, time)
		self._on_drag_end(None, None)

	def checkSanity(self, model, iter_to_copy, target_iter):
		path_of_iter_to_copy = model.get_path(iter_to_copy)
		path_of_target_iter = model.get_path(target_iter)
		if path_of_target_iter[0:len(path_of_iter_to_copy)] == path_of_iter_to_copy:
			return False
		else:
			return True
    
	def iterCopy(self, target_model, target_iter, row, pos):
		if (pos == gtk.TREE_VIEW_DROP_INTO_OR_BEFORE) or (pos == gtk.TREE_VIEW_DROP_INTO_OR_AFTER):
			new_iter = target_model.append(row)
		elif pos == gtk.TREE_VIEW_DROP_BEFORE:
			new_iter = target_model.insert_before(target_iter, row)
		elif pos == gtk.TREE_VIEW_DROP_AFTER:
			new_iter = target_model.insert_after(target_iter, row)
		
	def _on_drag_begin(self, widget, drag_context):
		self._dragging = True
	
	def _on_drag_end(self, widget, drag_context):
		self._dragging = False
		self._do_unselect()
	
	def _do_unselect(self):
		self._all_tags_treeview.get_selection().unselect_all()
		self._favorites_treeview.get_selection().unselect_all()
