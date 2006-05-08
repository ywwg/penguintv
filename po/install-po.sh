locale_name=$1
mkdir -p /usr/share/locale/$locale_name/LC_MESSAGES/
msgfmt $locale_name.po -o /usr/share/locale/$locale_name/LC_MESSAGES/penguintv.mo
