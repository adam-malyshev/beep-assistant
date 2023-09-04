#!/bin/sh
# launcher.sh
# navigate to home directory, then to this directory, then execute python script, then back home

cd /
cd home/beep/beep-assistant
sudo git pull
sudo pip install -r requirements.txt
cd /
