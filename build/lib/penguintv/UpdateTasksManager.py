# Written by Owen Williams
# see LICENSE for license information
import time
import threading

GUI = 0
DB = 1

class UpdateTasksManager:
	def __init__(self):
		self.gui_tasks = []
		self.db_tasks = []
		#self.db_= db_		
		self.task_list = []
		self.id_time=0
		self.time_appendix=0
#		self.lock = [threading.Lock(),threading.Lock()]
	
	def get_task_id(self):
		cur_time = int(time.time())
		
		if self.id_time == cur_time:
			self.time_appendix = self.time_appendix+1
		else:
			self.id_time = cur_time
			self.time_appendix=0
		
		return str(self.id_time)+"+"+str(self.time_appendix)
		
#	def lock_acquire(self, which):
#		self.lock[which].acquire()
		
#	def lock_release(self, which):
#		self.lock[which].release()
	
	def queue_task(self, t_type, func, arg=None, waitfor=None, clear_completed=True, priority=0):
		task_id = self.get_task_id()
		if t_type == GUI:
#			self.lock[GUI].acquire()
			if priority==1:
				self.gui_tasks.reverse()
			self.gui_tasks.append((func, arg, task_id, waitfor, clear_completed))	
			if priority==1:
				self.gui_tasks.reverse()
#			self.lock[GUI].release()
		elif t_type == DB:
#			self.lock[DB].acquire()
			if priority==1:
				self.db_tasks.reverse()
			self.db_tasks.append((func, arg, task_id, waitfor, clear_completed))	
			if priority==1:
				self.db_tasks.reverse()
#			self.lock[DB].release()
		else:
			raise BadArgument, t_type
		return task_id
					
	def peek_task(self, t_type, index=0):
		if t_type == GUI:
			if len(self.gui_tasks)>index:
				return self.gui_tasks[index]
			else:
				return None
		elif t_type == DB:
			if len(self.db_tasks)>index:
				return self.db_tasks[index]
			else:
				return None
		else:
			raise BadArgument, t_type
			
	def pop_task(self, t_type, index=0):
		if t_type == GUI:
			return self.gui_tasks.pop(index)
		elif t_type == DB:
			return self.db_tasks.pop(index)
		else:
			raise BadArgument, t_type
			
	def task_count(self, t_type):
		if t_type == GUI:
			return len(self.gui_tasks)
		elif t_type == DB:
			return len(self.db_tasks)
		else:
			raise BadArgument, t_type
		
	def is_completed(self, taskid):
		if taskid in self.task_list:
			return True
		return False
		
	def clear_completed(self, taskid):
		self.task_list.remove(taskid)
		
	def set_completed(self, taskid):
		self.task_list.append(taskid)			
		

class BadArgument(Exception):
	def __init__(self,arg):
		self.arg = arg
	def __str__(self):
		return "Bad Argument: "+self.arg
