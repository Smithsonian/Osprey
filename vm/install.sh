#!/bin/bash

if [ "$EUID" -ne 0 ]
  then echo "Please run as root"
  exit
fi

#FILE=../osprey/settings.py
#if [ ! -f "$FILE" ]; then
#    echo ""
#    echo " $FILE does not exist. Create it before running the installation"
#    echo ""
#fi
#
#FILE=../check_folder_md5/settings.py
#if [ ! -f "$FILE" ]; then
#    echo ""
#    echo " $FILE does not exist. Create it before running the installation"
#    echo ""
#fi

mkdir /usr/bin/osprey
mkdir /usr/bin/osprey/osprey
mkdir /var/log/osprey

wget https://raw.githubusercontent.com/Smithsonian/Osprey/master/image_validation/osprey.py -O osprey.py
wget https://raw.githubusercontent.com/Smithsonian/Osprey/master/image_validation/functions.py -O functions.py
wget https://raw.githubusercontent.com/Smithsonian/Osprey/master/image_validation/settings.py.template.py -O settings.py
wget https://raw.githubusercontent.com/Smithsonian/Osprey/master/image_validation/queries.py -O queries.py

mv osprey.py /usr/bin/osprey/osprey/
mv functions.py /usr/bin/osprey/osprey/
mv settings.py /usr/bin/osprey/osprey/
mv queries.py /usr/bin/osprey/osprey/


cp osprey_auto.sh /usr/bin/osprey/
cp osprey.service /etc/systemd/system/osprey.service

chmod 644 /etc/systemd/system/osprey.service
systemctl enable osprey.service

chmod -R 755 /usr/bin/osprey

echo ""
echo " Installation completed."
echo ""
echo " Edit the settings files:"
echo "     /usr/bin/osprey/osprey/settings.py"
echo ""

