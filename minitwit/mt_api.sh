#!/bin/bash
export FLASK_APP="./mt_api.py"
if [ $1 = '5003' ]; then
  flask initdb
  flask popdb
fi
flask run -p $1
