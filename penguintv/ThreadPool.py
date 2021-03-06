# Written by Owen Williams
# see LICENSE for license information
import threading
import logging
import time

try:
	import PyLucene
	HAS_LUCENE = True
except:
	HAS_LUCENE = False

# Ensure booleans exist (not needed for Python 2.2.1 or higher)
try:
	True
except NameError:
	False = 0
	True = not False

class ThreadPool:

	"""Flexible thread pool class.  Creates a pool of threads, then
	accepts tasks that will be dispatched to the next available
	thread."""

	def __init__(self, numThreads,name="ThreadPoolThread", lucene_compat=False, daemon=False):

		"""Initialize the thread pool with numThreads workers."""

		self.__threads = []
		self.__resizeLock = threading.Condition(threading.Lock())
		self.__taskLock = threading.Condition(threading.Lock())
		self.__tasks = []
		self.__isJoining = False
		self.__name = name
		self.__maxThreads = numThreads
		self.occupied_threads = 0
		self.lucene_compat = lucene_compat
		self._daemon = daemon
		#self.setThreadCount(numThreads)


#	def setThreadCount(self, newNumThreads):
#
#		""" External method to set the current pool size.  Acquires
#		the resizing lock, then calls the internal version to do real
#		work."""
#
#		# Can't change the thread count if we're shutting down the pool!
#		if self.__isJoining:
#			return False
#
#		self.__resizeLock.acquire()
#		try:
#			self.__setThreadCountNolock(newNumThreads)
#		finally:
#			self.__resizeLock.release()
#		return True
#
#	def __setThreadCountNolock(self, newNumThreads):
#
#		"""Set the current pool size, spawning or terminating threads
#		if necessary.  Internal use only; assumes the resizing lock is
#		held."""
#
#		# If we need to grow the pool, do so
#		while newNumThreads > len(self.__threads):
#			if self.lucene_compat:
#				newThread = LuceneThreadPoolThread(self,self.__name)
#			else:
#				newThread = ThreadPoolThread(self,self.__name)
#			self.__threads.append(newThread)
#			newThread.start()
#		# If we need to shrink the pool, do so
#		while newNumThreads < len(self.__threads):
#			self.__threads[0].goAway()
#			del self.__threads[0]

	def getThreadCount(self):

		"""Return the number of threads in the pool."""

		self.__resizeLock.acquire()
		try:
			return len(self.__threads)
		finally:
			self.__resizeLock.release()

	def getTaskCount(self):

		"""Return the number of queued items"""
		return len(self.__tasks)+self.occupied_threads

	def queueTask(self, task, args=None, taskCallback=None):

		"""Insert a task into the queue.  task must be callable;
		args and taskCallback can be None."""

		if self.__isJoining == True:
			return False
		if not callable(task):
			return False

		self.__resizeLock.acquire()
		i = 0
		deadlist = []
		for t in self.__threads:
			if not t.isAlive():
				deadlist.append(i)
			i+=1
		deadlist.reverse()
		for i in deadlist:
			#logging.debug("deleting dead thread %i" % i)
			del self.__threads[i]
		self.__resizeLock.release()

		self.__taskLock.acquire()
		try:
			self.__tasks.append((task, args, taskCallback))
			#logging.debug("max: %i, running: %i, used: %i,  tasks: %i start new?" % (self.__maxThreads, len(self.__threads), self.occupied_threads, len(self.__tasks)))
			if self.__maxThreads > len(self.__threads):
				#logging.debug("yes start new")
				if self.lucene_compat:
					newThread = LuceneThreadPoolThread(self,self.__name)
				else:
					newThread = ThreadPoolThread(self,self.__name)
				if self._daemon:
				  newThread.setDaemon(True)
				self.__threads.append(newThread)
				newThread.start()
			#else:
			#	logging.debug("no, thread limit or some unoc")
			return True
		finally:
			self.__taskLock.release()

	def getNextTask(self):

		""" Retrieve the next task from the task queue.  For use
		only by ThreadPoolThread objects contained in the pool."""

		self.__taskLock.acquire()
		try:
			if self.__tasks == []:
				return (None, None, None)
			else:
				task, args, taskCallback = self.__tasks.pop(0)
				if not callable(task):
					logging.warning("task no longer callable, skipping")
					return (None, None, None)
				return (task, args, taskCallback)
		finally:
			self.__taskLock.release()

	def joinAll(self, waitForTasks = True, waitForThreads = True):

		""" Clear the task queue and terminate all pooled threads,
		optionally allowing the tasks and threads to finish."""

		# Mark the pool as joining to prevent any more task queueing
		self.__isJoining = True

		# Wait for tasks to finish
		if waitForTasks:
			while self.__tasks != []:
				time.sleep(.1)
		else:
			self.__tasks = []

		# Tell all the threads to quit
		self.__resizeLock.acquire()
		try:
			self.__isJoining = True

			# Wait until all threads have exited
			if waitForThreads:
				while len(self.__threads)>0:
					self.__threads[0].goAway()
					self.__threads[0].join(6)
					del self.__threads[0]
			else:
				while len(self.__threads)>0:
					del self.__threads[0]

			# Reset the pool for potential reuse
			self.__isJoining = False
		finally:
			self.__resizeLock.release()

class ThreadPoolThread(threading.Thread):

	""" Pooled thread class. """

	threadSleepTime = 1.0

	def __init__(self, pool, n="ThreadPoolThread"):

		""" Initialize the thread and remember the pool. """

		threading.Thread.__init__(self,name=n)
		self.__pool = pool
		self.__isDying = False

	def run(self):

		""" Until told to quit, retrieve the next task and execute
		it, calling the callback if any.  """
		start_time = time.time()
		while self.__isDying == False:
			cmd, args, callback = self.__pool.getNextTask()
			# If there's nothing to do, die
			if cmd is None:
				#logging.debug("nothing to do")
				if time.time() - start_time > 10:
					#logging.debug("dying")
					break
				time.sleep(ThreadPoolThread.threadSleepTime)
				continue
			if callback is None:
				self.__pool.occupied_threads+=1
				#logging.debug("max: %i, running: %i, used: %i,  tasks: %i" % (self.__pool._ThreadPool__maxThreads, len(self.__pool._ThreadPool__threads), self.__pool.occupied_threads, len(self.__pool._ThreadPool__tasks)))
				cmd(args)
				self.__pool.occupied_threads-=1
			else:
				self.__pool.occupied_threads+=1
				#logging.debug("max: %i, running: %i, used: %i,  tasks: %i" % (self.__pool._ThreadPool__maxThreads, len(self.__pool._ThreadPool__threads), self.__pool.occupied_threads, len(self.__pool._ThreadPool__tasks)))
				callback(cmd(args))
				self.__pool.occupied_threads-=1
			start_time = time.time()

	def goAway(self):

		""" Exit the run loop next time through."""

		self.__isDying = True

#if HAS_LUCENE:
#	l_threadclass = PyLucene.PythonThread
#else:
#	l_threadclass = threading.Thread

#this class will never get called if we don't have lucene, but we need to declare it
#even if we don't have the library (no preprocessors in python)
#class LuceneThreadPoolThread(l_threadclass):
#
#	""" Pooled thread class. """
#
#	threadSleepTime = 0.5
#
#	def __init__(self, pool, n="LuceneThreadPoolThread"):
#
#		""" Initialize the thread and remember the pool. """
#
#		l_threadclass.__init__(self,name=n)
#		self.__pool = pool
#		self.__isDying = False
#
#	def run(self):
#
#		""" Until told to quit, retrieve the next task and execute
#		it, calling the callback if any.  """
#
#		while self.__isDying == False:
#			cmd, args, callback = self.__pool.getNextTask()
#			# If there's nothing to do, just sleep a bit
#			if cmd is None:
#				time.sleep(LuceneThreadPoolThread.threadSleepTime)
#			elif callback is None:
#				self.__pool.occupied_threads+=1
#				cmd(args)
#				self.__pool.occupied_threads-=1
#			else:
#				self.__pool.occupied_threads+=1
#				callback(cmd(args))
#				self.__pool.occupied_threads-=1
#
#	def goAway(self):
#
#		""" Exit the run loop next time through."""
#
#		self.__isDying = True
