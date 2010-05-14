#!/usr/bin/python
import base64
import os
import time
import uuid

import subprocess
import sys
from subprocess import PIPE
import httplib
from urllib import urlencode
from urllib2 import urlopen, Request, HTTPRedirectHandler
import urllib2
import urllib
from cookielib import * 
from urlparse import urlparse

CURL_CMD = 'curl' #if curl is in your path/linux
# CURL_CMD = 'c:\curl\curl.exe' #if curl is in your path/linux

USER_AGENT = 'CCHQ-submitfromfile-python-v0.1' 

#TARGET_URL = "http://{{remote_host}}/builds/new"
TARGET_URL = "http://{{remote_host}}/releasemanager/new_jarjad/"

class AuthenticatedHandler(object):    
    def __init__(self, username, password, hostname):
        self.username=username
        self.password=password
        self.hostname=hostname
        self.session_cookie=''        
        self.cookie_header = ''

        self._establishSession()
    
    def _establishSession(self):
        self.session_cookie = os.path.join(os.path.dirname(__file__),str(uuid.uuid1()) + "_cookie.txt")
        p = subprocess.Popen([CURL_CMD,'-c',self.session_cookie, '-F username=%s' % self.username, '-F password=%s' % self.password,'--request', 'POST', 'http://%s/accounts/login/' % hostname],stdout=PIPE,stderr=PIPE,shell=False)
        results = p.stdout.read()
        
        
    def get_url(self, remote_host):
        return TARGET_URL.replace("{{remote_host}}", remote_host)

    def do_upload_build(self,
                        hostname,
                        project_id, 
                        version,
                        revision_number,
                        build_number,
                        jar_file,
                        jad_file,
                        description):
        try:
#            fin = open(jar_file,'r')
#            jarfile_str= fin.read()
#            fin.close()
#            
#            fin = open(jad_file,'r')
#            jadfile_str= fin.read()
#            fin.close()

            command_arr = [CURL_CMD,'-b', 
                                  self.session_cookie,
                                  "-s",
                                  "--user-agent", USER_AGENT,
                                  '-F jar_file_upload=@%s' % jar_file, 
                                  '-F jad_file_upload=@%s' % jad_file, 
                                  '-F project=%s' % project_id,                                  
                                  '-F build_number=%s' % build_number,
                                  '-F revision_number=%s' % revision_number,                                  
                                  '-F version=%s' % version,
                                  '-F description=%s' % urllib.quote(description),                                  
                                  '--request', 'POST', self.get_url(self.hostname)]
            
            
            p = subprocess.Popen(command_arr,
                                  stdout=PIPE,stderr=PIPE,shell=False)
            
            print ' '.join(command_arr)
            results = p.stdout.read()
            errors = p.stderr.read()
            print results
            if errors.strip() != '': print "ERROR: %s" % errors
            
        except Exception, e:
            print "Error uploading submission: " + str(e)
        finally:
            pass
        



if __name__ == "__main__":
    
    try:       
        hostname = os.environ['hostname']
        username = os.environ['username']
        password = os.environ['password']
        
        project_id = os.environ['project_id']        
        version = os.environ['version']
        revision_number = os.environ['revision_number']
        build_number = os.environ['build_number']
        jar_file = os.environ['jar_file_path']
        jad_file = os.environ['jad_file_path']
        description = os.environ['description']  
    except Exception, e:
        #no environmental variables, check to see if the arguments are there in the cmdline
        if len(sys.argv) < 11:
            print e
            print """\tUsage: 
                submit_build.py
                     <remote hostname> 
                     <remote username> 
                     <remote password>                      
                     <project_id>                     
                     <version>
                     <build_number>
                     <revision_number>                     
                     <jar_file_path>
                     <jad_build_path>                     
                     <description>                     
                    """                    
            sys.exit(1)
        else:
            hostname = sys.argv[1]
            username = sys.argv[2]
            password = sys.argv[3]
            version = sys.argv[4]
            project_id = sys.argv[5]        
            build_number = sys.argv[6]
            revision_number = sys.argv[7]                    
            jar_file = sys.argv[8]
            jad_file = sys.argv[9]
            description = ' '.join(sys.argv[10:])

    uploader = AuthenticatedHandler(username,password,hostname)
    uploader.do_upload_build(hostname,
                             project_id, 
                             version,
                             revision_number,
                             build_number,
                             jar_file,
                             jad_file,
                             description)
