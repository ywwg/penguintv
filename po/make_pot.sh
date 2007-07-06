cd ..
cat MANIFEST MANIFEST-OLPC | sort -u | grep -v feedparser |grep \\\.py | sed -e 's/$/ /' | tr -d '\n' | xargs xgettext --copyright-holder="Owen Williams" --msgid-bugs-address="owen-bugs@ywwg.com"
mv messages.po ./po/penguintv.pot
cd ./po
intltool-extract --type "gettext/glade" ../share/penguintv.glade
xgettext -k_ -kN_ -o messages2.pot ../share/penguintv.glade.h
cat messages2.pot >> penguintv.pot
rm messages2.pot
gedit penguintv.pot
