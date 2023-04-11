#!/usr/bin/env python
from flask import Flask, request, send_file, Blueprint
import os
import sys
import io
import requests
from flask.json import jsonify
import jwt
from random import randint
import datetime

def validate_jwt(func):
    def wrapped():
        token = request.headers.get("jwt")
        if not token:
            return jsonify({'message':'Missing token'}), 403
        try:
            decoded = jwt.decode(
                token, 
                key=os.getenv('JWT_AUTHENTICATION_KEY'), 
                algorithms=["HS256"])
        except:
            return jsonify({'message':"Invalid token"}),403
        return func()
    return wrapped