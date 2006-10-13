#thanks to http://www.daa.com.au/pipermail/pygtk/2003-November/006304.html
#for the reordering code

import gtk
import pango
from ptvDB import T_ALL, T_TAG, T_SEARCH, T_BUILTIN
from FeedList import ALL, DOWNLOADED
from MainWindow import F_TEXT, F_COUNT, F_SEPARATOR, F_FAVORITE, F_NOT_FAVORITE, F_TYPE

class FilterSelectorWidget:
	def __init__(self, glade_path, main_window, model):
		self._xml_complex = gtk.glade.XML(glade_path, 'filter_selector_widget_with_tags','penguintv')
		self._xml_simple  = gtk.glade.XML(glade_path, 'filter_selector_widget_no_tags','penguintv')
		self._main_window = main_window
		self._model = model
		
		self._complex_widget = self._xml_complex.get_widget('filter_selector_widget_with_tags')
		self._simple_widget  = self._xml_simple.get_widget('filter_selector_widget_no_tags')
		self._pane = self._xml_complex.get_widget('hpaned')
		self._favorites_treeview = self._xml_complex.get_widget('favorites_treeview')
		self._favorites_model =  gtk.ListStore(str, #name of filter
											   str, #text to display
											   int) #original id
		self._favorites_treeview.set_model(self._favorites_model)

		column = gtk.TreeViewColumn(_('Favorites'))
		renderer = gtk.CellRendererText()
		column.pack_start(renderer)
		column.set_attributes(renderer, text=1)
		self._favorites_treeview.append_column(column)
		
		self._all_tags_treeview = self._xml_complex.get_widget('all_tags_treeview')
		self._all_tags_filter = self._model.filter_new()
		self._all_tags_filter.set_visible_column(F_NOT_FAVORITE)
		self._all_tags_treeview.set_model(self._all_tags_filter)
		
		column = gtk.TreeViewColumn(_('All Tags'))
		renderer = gtk.CellRendererText()
		column.pack_start(renderer)
		column.set_attributes(renderer, text=F_COUNT)
		self._all_tags_treeview.append_column(column)
		
		self._all_tags_treeview.set_row_separator_func(lambda model,iter: model[model.get_path(iter)[0]][F_SEPARATOR])
		self._xml_complex.get_widget('all_feeds_button').connect('clicked', self._select_all_feeds)
		self._xml_complex.get_widget('downloaded_media_button').connect('clicked', self._select_downloaded_media)
		
		self._xml_simple.get_widget('all_feeds_button').connect('clicked', self._select_all_feeds)
		self._xml_simple.get_widget('downloaded_media_button').connect('clicked', self._select_downloaded_media)
		
		self._TARGET_TYPE_INTEGER = 80
		self._TARGET_TYPE_REORDER = 81
		drop_types = [ ('reorder',gtk.TARGET_SAME_WIDGET,self._TARGET_TYPE_REORDER),
					   ('integer',gtk.TARGET_SAME_APP,self._TARGET_TYPE_INTEGER)]
		#for removing items from favorites and reordering
		self._favorites_treeview.enable_model_drag_source(gtk.gdk.BUTTON1_MASK, drop_types, gtk.gdk.ACTION_COPY)
		self._all_tags_treeview.drag_dest_set(gtk.DEST_DEFAULT_ALL, drop_types, gtk.gdk.ACTION_COPY)
		
		#copying items to favorites
		self._favorites_treeview.enable_model_drag_dest(drop_types, gtk.gdk.ACTION_COPY)
		self._all_tags_treeview.drag_source_set(gtk.gdk.BUTTON1_MASK, drop_types, gtk.gdk.ACTION_COPY)
		
		self._dragging = False
		
		for key in dir(self.__class__): #python insaneness
			if key[:3] == '_on':
				self._xml_complex.signal_connect(key, getattr(self, key))
		
		self._old_list = []
		
	def is_visible(self):
		return self._complex_widget.get_property('visible') or self._simple_widget.get_property('visible')
		
	def ShowAt(self, x, y):
		context = self._complex_widget.create_pango_context()
		style = self._complex_widget.get_style().copy()
		font_desc = style.font_desc
		metrics = context.get_metrics(font_desc, None)
		char_width = metrics.get_approximate_char_width()
		
		widest_left = 0
		widest_right = 0
		
		has_tags = False
		
		self._favorites_model.clear()
		self._favorites_old_order = []
		
		i=-1
		for row in self._model:
			i+=1
			if row[F_FAVORITE] > 0:
				self._favorites_old_order.append([row[F_FAVORITE],row[F_TEXT],row[F_COUNT],i])
			if row[F_TYPE] == T_BUILTIN or row[F_FAVORITE] > 0:
				width = len(row[F_COUNT])
				if width > widest_left:
					widest_left = width
			if row[F_NOT_FAVORITE]:
				has_tags = True
				width = len(row[F_COUNT])
				if width > widest_right:
					widest_right = width
					
		self._favorites_old_order.sort()
		for row in self._favorites_old_order:
			self._favorites_model.append(row[1:])
		
		pane_position = pango.PIXELS((widest_left+10)*char_width)
		window_width  = pango.PIXELS((widest_left+widest_right+10)*char_width)+100
		
		if has_tags:
			widget = self._complex_widget
			self._complex_widget.move(x,y)
			self._complex_widget.resize(window_width,500)
			self._pane.set_position(pane_position)
			self._all_tags_filter.refilter()
			self._favorites_treeview.columns_autosize()
			self._all_tags_treeview.columns_autosize()
			self._complex_widget.show_all()
		else:
			self._simple_widget.move(x,y)
			self._simple_widget.show_all()
						
	def Hide(self):
		self._all_tags_treeview.get_selection().unselect_all()
		self._favorites_treeview.get_selection().unselect_all()
		self._complex_widget.hide()
		self._simple_widget.hide()
		new_order = [r[0] for r in self._favorites_model]
		old_order = [r[1] for r in self._favorites_old_order]
		if old_order != new_order:
			i=0
			for tag in new_order:
				i+=1
				self._main_window.set_tag_favorite(tag, i)
				
	def _on_button_release_event(self, button, event):
		if not self._dragging:
			selection = self._favorites_treeview.get_selection()
			model, iter = selection.get_selected()
			if iter is not None:
				i=-1
				for row in self._model:
					i+=1
					if row[F_TEXT] == model[iter][F_TEXT]:
						break
				self._main_window.set_active_filter(i)
				self.Hide()
				selection.unselect_all()
				return
				
			selection = self._all_tags_treeview.get_selection()
			model, iter = selection.get_selected()
			if iter is not None:
				i=-1
				for row in self._model:
					i+=1
					if row[F_TEXT] == model[iter][F_TEXT]:
						break
				self._main_window.set_active_filter(i)
				self.Hide()
				selection.unselect_all()
				return
			
	def _select_all_feeds(self, button):
		self._main_window.set_active_filter(ALL)
		self.Hide()
		
	def _select_downloaded_media(self, button):
		self._main_window.set_active_filter(DOWNLOADED)
		self.Hide()
		
	def _on_all_tags_treeview_drag_data_get(self, treeview, drag_context, selection_data, info, time):
		selection = treeview.get_selection()
		model, iter = selection.get_selected()
		path = model.get_path(iter)
		selection_data.set(selection_data.target, 8, str(path[0]))
		
	def _on_favorites_treeview_drag_data_get(self, treeview, drag_context, selection_data, info, time):
		selection = treeview.get_selection()
		model, iter = selection.get_selected()
		path = model.get_path(iter)
		selection_data.set(selection_data.target, 8, str(path[0]))
		
	def _on_all_tags_treeview_drag_data_received(self, widget, context, x, y, selection, targetType, time):
		widget.emit_stop_by_name('drag-data-received')
		if targetType == self._TARGET_TYPE_INTEGER:
			#print "got",selection.data
			tag_index = ""
			for c in selection.data:
				if c != "\0":  #for some reason ever other character is a null.  what gives?
					tag_index = tag_index+c
			index = int(tag_index)
			target_iter = self._favorites_model.get_iter((index,))
			self._main_window.set_tag_favorite(self._favorites_model[index][0], 0)
			self._favorites_model.remove(target_iter)
		
	def _on_favorites_drag_data_received(self, treeview, context, x, y, selection, targetType, time):
		treeview.emit_stop_by_name('drag-data-received')
		if targetType == self._TARGET_TYPE_INTEGER:
			tag_index = ""
			for c in selection.data:
				if c != "\0":  #for some reason ever other character is a null.  what gives?
					tag_index = tag_index+c
			index = int(tag_index)
			#self._main_window.set_tag_favorite(self._all_tags_filter[index][F_TEXT], )
			source_row = self._all_tags_filter[index]
			for row in self._favorites_model:
				if source_row[F_TEXT] == row[0]:
					return
			new_row = [source_row[F_TEXT],source_row[F_COUNT],index]
			try:
				path, pos = treeview.get_dest_row_at_pos(x, y)
				dest_iter = self._favorites_model.get_iter(path)
				#self._favorites_model.insert_after(dest_iter, new_row)
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

	def checkSanity(self, model, iter_to_copy, target_iter):
		path_of_iter_to_copy = model.get_path(iter_to_copy)
		path_of_target_iter = model.get_path(target_iter)
		if path_of_target_iter[0:len(path_of_iter_to_copy)] == path_of_iter_to_copy:
			return False
		else:
			return True
    
	def iterCopy(self, target_model, target_iter, row, pos):
		if (pos == gtk.TREE_VIEW_DROP_INTO_OR_BEFORE) or (pos == gtk.TREE_VIEW_DROP_INTO_OR_AFTER):
			new_iter = target_model.prepend(row)
		elif pos == gtk.TREE_VIEW_DROP_BEFORE:
			new_iter = target_model.insert_before(target_iter, row)
		elif pos == gtk.TREE_VIEW_DROP_AFTER:
			new_iter = target_model.insert_after(target_iter, row)
		
	def _on_drag_begin(self, widget, drag_context):
		self._dragging = True
	
	def _on_drag_end(self, widget, drag_context):
		self._dragging = False
