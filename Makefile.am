SUBDIRS = share penguintv activity

activitydir = $(datadir)/sugar/activities/ptv
activity_PYTHON =              	\
		__init__.py 			\
		PenguinTVActivity.py

EXTRA_DIST =       \
			activity-penguintv.svg \
			penguintv.activity

install-data-local:
		sugar-setup-activity $(srcdir)/penguintv.activity
