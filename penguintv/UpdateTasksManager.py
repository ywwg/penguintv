# Written by Owen Williams
# see LICENSE for license information
import time
import traceback, sys

import gobject
import threading

#the manager can either run tasks as a gobject idler, as a thread,
#or it can let the application decide when to run the generator

GOBJECT=0
THREADED=1
MANUAL=2

FLUSH_TIME = 60*10

class UpdateTasksManager:
	task_list = []
	id_time = 0
	time_appendix = 0

	def __init__(self, style=GOBJECT, name=""):
		self.style = style
		self.threadSleepTime = 0.5
		self.updater_running = False
		self.my_tasks = []
		self.name = name
		
	def get_task_id(self):
		cur_time = int(time.time())
		
		if UpdateTasksManager.id_time == cur_time:
			UpdateTasksManager.time_appendix = UpdateTasksManager.time_appendix+1.0
		else:
			UpdateTasksManager.id_time = cur_time
			UpdateTasksManager.time_appendix=0.0
		
		return float(UpdateTasksManager.id_time)+(UpdateTasksManager.time_appendix/100)
			
	def queue_task(self, func, arg=None, waitfor=None, clear_completed=True, priority=0):
		task_id = self.get_task_id()
		if priority==1:
			self.my_tasks.reverse()
		self.my_tasks.append((func, arg, task_id, waitfor, clear_completed))	
		if priority==1:
			self.my_tasks.reverse()
		if self.updater_running == False:
			self.updater_running = True
			if self.style == GOBJECT:
				gobject.timeout_add(100, self.updater_gen().next)
			elif self.style == THREADED:
				threading.Thread(self.updater_thread)
			#elif manual, do nothing
		return task_id
					
	def peek_task(self, index=0):
		if len(self.my_tasks)>index:
			return self.my_tasks[index]
		else:
			return None
			
	def pop_task(self, index=0):
		return self.my_tasks.pop(index)
			
	def task_count(self):
		return len(self.my_tasks)
		
	def is_completed(self, taskid):
		if taskid in UpdateTasksManager.task_list:
			return True
		return False
		
	def clear_completed(self, taskid):
		UpdateTasksManager.task_list.remove(taskid)
		
	def set_completed(self, taskid):
		UpdateTasksManager.task_list.append(taskid)	
		
	def updater_thread(self):
		for item in self.updater_gen():
			time.sleep(self.threadSleepTime)
			
	def updater_timer(self):
		self.updater_running = True
		for item in self.updater_gen(True):
			pass
		if self.task_count() > 0: # we didn't finish
			return True
		self.updater_running = False
		return False
		
	def updater_gen(self,timed=False):
		"""Generator that empties that queue and yields on each iteration"""
		skipped=0
		while self.task_count() > 0: #just run forever
			var = self.peek_task(skipped)
			if var is None: #ran out of tasks
				skipped=0
				yield True
				continue
			func, args, task_id, waitfor, clear_completed =  var
			
			if waitfor:
				if self.is_completed(waitfor): #don't pop if false
					try:
						if type(args) is tuple:
							func(*args)
						elif args is not None:
							func(args)
						else:
							func()
					except:
						exc_type, exc_value, exc_traceback = sys.exc_info()
						error_msg = ""
						for s in traceback.format_exception(exc_type, exc_value, exc_traceback):
							error_msg += s
					self.set_completed(task_id)
					if clear_completed:
						self.clear_completed(waitfor)
					self.pop_task(skipped)
				else:
					if time.time() - task_id > FLUSH_TIME:
						self.pop_task(skipped)
					skipped = skipped+1
			else:
				try:
					if type(args) is tuple:
						func(*args)
					elif args is not None:
						func(args)
					else:
						func()
				except:
					exc_type, exc_value, exc_traceback = sys.exc_info()
					error_msg = ""
					for s in traceback.format_exception(exc_type, exc_value, exc_traceback):
						error_msg += s
					print error_msg
				self.set_completed(task_id)
				self.pop_task(skipped)
			yield True
		if not timed:
			self.updater_running = False
		#print self.name+" out of updater"
		yield False		
		

class BadArgument(Exception):
	def __init__(self,arg):
		self.arg = arg
	def __str__(self):
		return "Bad Argument: "+self.arg
