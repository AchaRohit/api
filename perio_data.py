#!/usr/bin/env python
from flask import Flask, request, send_file, Blueprint
import os
import sys

import requests
from flask.json import jsonify
import logging

import io
from io import BytesIO
from PyPDF2 import PdfReader, PdfWriter

from utils import *

perio_data = Flask(__name__)


@perio_data.route('/', methods=['POST'], endpoint='fn_perio_data')
# @validate_jwt
def fn_perio_data():
    logging.basicConfig(level=logging.INFO,  format='%(asctime)s - %(levelname)s - %(message)s')

    logging.info('IDP-PRE-PROCESS : facesheetextraction :  facesheetextraction : Received a request')

    if request.method != 'POST':
        return jsonify(
                    message="Invalid Action- Should be POST",
                    category="error",
                    status=500)
    
    request_data = request.get_data()
    if request_data:
        if request_data is None:
            return jsonify(
                    message="Byte array is empty",
                    category="error",
                    status=400), 400
        try:
            # PDF part 
            # bytesio = BytesIO(request_data)
            # reader = PdfReader(BytesIO(bytesio))

            # JSON part
            # json_bytes = BytesIO(request_data)
            myjson = json.loads(request_data)
            
        except Exception as ex:
            logging.error('PERIO DATA-PRE-PROCESS : perio data extraction :  : Error decoding byte array: ' + str(ex))
            return jsonify(
                    message="Unexpected Error in Error decoding byte array:: " + str(ex),
                    category="error",
                    status=500), 500
        
        # load files
#         try:
#             auth_user = os.getenv('OSCP_NP_USER')
#             auth_password = os.getenv('OSCP_NP_PASS')    

           
#             logging.info('IDP-PRE-PROCESS : facesheetextraction :  facesheetextraction : Username is ' +  auth_user )
#             if auth_user is None:
#                 print("Unable to read username", sys.exc_info()[0])
#                 return jsonify(
#                         message="Unable to read username",
#                         category="error",
#                         status=500)

#             if auth_password is None:
#                 print("Unable to read password", sys.exc_info()[0])
#                 return jsonify(
#                         message="Unable to read password",
#                         category="error",
#                         status=500)
                  
            
#             file_path = os.getenv('FACESHEETEXTRACTION_2827_MODELSPATH')    
#             if file_path is None:
#                 print("Unable to find directory", sys.exc_info()[0])
#                 return jsonify(
#                         message="Unable to find FACESHEETEXTRACTION_2827_MODELSPATH directory",
#                         category="error",
#                         status=500)                  
#             logging.info('IDP-PRE-PROCESS : facesheetextraction :  facesheetextraction : Directory is ' +  file_path )                        
                        
# #            file_path = './api/2827/'
#             hospitalfile = os.path.join(file_path,"hospitals.txt")
            
#             #ipcmgrid = os.path.join(file_path, "IPCMGrid.xlsx")
#             ipcmgrid = os.path.join(file_path, "IPCMGrid.zip")
#             ipcmgridCPF = os.path.join(file_path, "IPCMGridCPF.pickled")
#             icd10_file = os.path.join(file_path, "icd10_codes.xlsx")
            
#             fieldkeysFile = os.path.join(file_path, "fieldkeys.json")
#             keyValueOverrideFile = os.path.join(file_path, "keyValueOverrides.json")
#             briaApiJsonTemplateFile = os.path.join(file_path,"bria_idp_api_request_template.json")

                       
#             with smbclient.open_file(fieldkeysFile, mode="r",username=auth_user, password=auth_password,share_access="r") as fieldkeysFD:
#                 fieldKeys = json.load(fieldkeysFD)

#             with smbclient.open_file(briaApiJsonTemplateFile, mode="r",username=auth_user, password=auth_password,share_access="r") as briaApiJsonTemplateFD:
#                 briaApiJson = json.load(briaApiJsonTemplateFD)

#             with smbclient.open_file(keyValueOverrideFile, mode="rb",username=auth_user, password=auth_password,share_access="r") as keyValueOverrideFD:
#                 keyValueOverrides = json.load(keyValueOverrideFD)
            

        
#         except Exception as ex:
#             logging.error('IDP-PRE-PROCESS : facesheetextraction :  facesheetextraction : Unexpected Error in facesheetextraction-1 request : ' + str(ex))
#             return jsonify(
#                         message="Unexpected Error in facesheetextraction: " + str(ex),
#                         category="error",
#                         status=420)
        
        
        try: 
            all_teeth_char_list = []

            serialized_json, meta_data = serialize_json(myjson)
            window_wise_list = window_search_using_serialized_JSON(serialized_json, meta_data)
            column_extents, col_width, window_wise_list, end_positions, perio_page = get_dcm_with_fuzzy(window_wise_list)
            if end_positions == (0, 0):
                found, tooth_list, window_wise_list, perio_page = find_tooth_window_and_deactivate(window_wise_list)
                if found == "Completed":
                    all_tooth_pos, col_width = complete_tooth_puzzle(tooth_list, found)
                    column_extents, end_positions = find_column_extents(all_tooth_pos, col_width)
                else:
                    print("\tBoth didn't work..!!")
                    logging.info("PERIO DATA  : '\tBoth didn't work..!!'", message)

            message=""
            
            try:
                window_wise_list = isolate_perio_page(window_wise_list, perio_page)
            except Exception as ex:
                message = message + "/" + "Failure in isolating perio page: " + str(ex)
                logging.info("PERIO DATA  :", message)
                pass

            try:
                window_wise_list = superactivate_keyword_windows(window_wise_list)
            except Exception as ex:
                message = message + "/" + "Failure in superactivate_keyword_windows: " + str(ex)
                logging.info("PERIO DATA  :", message)
                pass

            try:
                dates, window_wise_list = get_dates(window_wise_list)
            except Exception as ex:
                message = message + "/" + "Failure in get_dates: " + str(ex)
                logging.info("PERIO DATA  :", message)
                pass

            try:
                max_date = get_max_date(dates)              
            except Exception as ex:
                message = message + "/" + "Failure in get_max_date: " + str(ex)
                logging.info("PERIO DATA  :", message)
                pass
                    
            try:                         
                window_wise_list = status_correction_for_dates(dates, max_date, window_wise_list)
            except Exception as ex:
                message = message + "/" + "Failure in status_correction_for_dates: " + str(ex)
                logging.info("PERIO DATA  :", message)
                pass
                    
            try:                         
                window_wise_list = deactivate_alphabetes_only(window_wise_list)
            except Exception as ex:
                message = message + "/" + "Failure in deactivate_alphabetes_only: " + str(ex)
                logging.info("PERIO DATA  :", message)
                pass
                    
            try:                         
                window_wise_list = remove_left_right_words(end_positions, window_wise_list)
            except Exception as ex:
                message = message + "/" + "Failure in remove_left_right_words: " + str(ex)
                logging.info("PERIO DATA  :", message)
                pass

            try:                         
                activated_serialized_json = create_activated_serialized_json(window_wise_list)
            except Exception as ex:
                message = message + "/" + "Failure in create_activated_serialized_json: " + str(ex)
                logging.info("PERIO DATA  :", message)
                pass

            try:                  
                activated_window_wise_list = window_search_using_serialized_JSON(activated_serialized_json, meta_data)
            except Exception as ex:
                message = message + "/" + "Failure in activated window_search_using_serialized_JSON: " + str(ex)
                logging.info("PERIO DATA  :", message)
                pass
                    
            try:  
                top_4_list, top_4_idx = find_top_4_row(activated_window_wise_list)
            except Exception as ex:
                message = message + "/" + "Failure in find_top_4_row: " + str(ex)
                logging.info("PERIO DATA  :", message)
                pass
                    
            try:                  
                tooth_char_mapping_list = tooth_char_mapping_from_top_4(top_4_list, column_extents)
            except Exception as ex:
                message = message + "/" + "Failure in tooth_char_mapping_from_top_4: " + str(ex)
                logging.info("PERIO DATA  :", message)
                pass

            try:                     
                all_teeth_char_list = final_tooth_char_mapping(tooth_char_mapping_list)
                print("-------------------------------------------------------------------------------------------")
            except Exception as ex:
                message = message + "/" + "Failure in final_tooth_char_mapping: " + str(ex)
                logging.info("PERIO DATA  :", message)
                pass

            return jsonify(all_teeth_char_list, message=message, category="Success", status=200)
            
        except Exception as ex:
            logging.error("PERIO DATA  : facesheetextraction : Unexpected Error in facesheetextraction3: ' + str(ex)")
            return jsonify(
                        message="Unexpected Error in PERIO DATA: " + str(ex),
                        category="error",
                        status=420)
        


if __name__ == '__main__':
    perio_data.run(debug=True)