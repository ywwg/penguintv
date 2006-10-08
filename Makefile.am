SUBDIRS = share penguintv

activitydir = $(datadir)/sugar/activities/ptv
activity_PYTHON =              	\
		__init__.py 			\
		PenguinTVActivity.py

EXTRA_DIST = penguintv.activity

install-data-local:
		sugar-setup-activity $(srcdir)/penguintv.activity
