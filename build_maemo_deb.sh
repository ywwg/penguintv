#!/bin/sh

EMBEDDED_ICON="./share/pixmaps/26x26/penguintvicon.png"

if [ "$1"x == "x" ] ; then
	echo "Need a GPG key to sign with (with 0x) (try gpg --list-keys, use the 8 digit hex num)"
	exit 1
fi

GPG_KEY="$1"

./packaging/setup-py2deb.py
if [ $? -ne 0 ] ; then
	echo "There was an error with the py2deb process, stopping"
	exit 1
fi

cd deb-build
for d in `find ./ -maxdepth 1 -type d | sort` ; do
	builddir=$d
done
cd $builddir

# Set up icon which will appear in application manager
iconfile=`tempfile`
if [ ! -f $EMBEDDED_ICON ] ; then
	echo "can't find icon"
	exit 1 
fi

#need to apt-get install sharutils for this stepp
uuencode -m $EMBEDDED_ICON /dev/stdout > $iconfile
length=`cat $iconfile | wc -l`

echo -e \\n"XB-Maemo-Icon-26:" >> debian/control
#cut the first and last lines from the file, then add a leading space
cat $iconfile | sed -n '1d; $d; p' | sed 's/^/ /' >> debian/control

#build the final package
dpkg-buildpackage -rfakeroot -sa
cd ..
debsign -k$GPG_KEY *.changes

if [ "$?" == "0" ] ; then
	echo ""
	echo "build complete, ready to upload to extras assistant.  Files are in deb-build/"
fi
