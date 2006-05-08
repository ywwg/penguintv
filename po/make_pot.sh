cd ../penguintv
pygettext penguintv.py utils.py MediaManager.py BTDownloader.py EntryList.py FeedList.py HTTPDownloader.py EntryView.py
mv messages.pot ../po/penguintv.pot
cd ../po
intltool-extract --type "gettext/glade" ../share/penguintv.glade
xgettext -k_ -kN_ -o messages2.pot ../share/penguintv.glade.h
cat messages2.pot >> penguintv.pot
rm messages2.pot
gedit penguintv.pot
