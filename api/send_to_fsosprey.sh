#!/bin/bash
#
# Send the dashboard files to the DEV machine

rsync -ruth --progress --exclude="__pycache__" --exclude="requirements.txt" --exclude="settings.py" --exclude="settings.py.*" --exclude="cache" --exclude="image_previews" --exclude="logs" --exclude="venv" --exclude="*.bat" --exclude="*.sh" --exclude="*.code-workspace" --exclude=".idea" . si-fsosprey01.si.edu:/var/www/html/

rsync -ruth --progress --exclude="__pycache__" --exclude="requirements.txt" --exclude="settings.py" --exclude="settings.py.*" --exclude="cache" --exclude="image_previews" --exclude="logs" --exclude="venv" --exclude="*.bat" --exclude="*.sh" --exclude="*.code-workspace" --exclude=".idea" . si-fsosprey02.si.edu:/var/www/api/
