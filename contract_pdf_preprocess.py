##########################PRE PROCESS PDF FOR CONTRACT COMAPRE#####################
from flask import request, Blueprint
import os
import sys
from flask.json import jsonify
import smbclient 
import logging
from validate_jwt import validate_jwt
import pikepdf
from pikepdf import Pdf, Page, Operator, parse_content_stream, unparse_content_stream
from io import BytesIO
import re

contract_pdf_preprocess = Blueprint('contract_pdf_preprocess', __name__)

@contract_pdf_preprocess.route(
    '/preprocesspdf', methods=['POST'], endpoint='fn_remove_black_box')
# @validate_jwt
def fn_remove_black_box():
    logging.basicConfig(level=logging.INFO,  format='%(asctime)s - %(levelname)s - %(message)s')
    logging.info('IDP-PRE-PROCESS : preprocesspdf :  contract_pdf_preprocess : Received a request')
    if request.method != 'POST':
        return jsonify(
                    message="Invalid Action- Should be POST",
                    category="error",
                    status=500)    
    try:
        # import pdb;pdb.set_trace()
        request_data = request.get_json()
        if request_data:
            if 'InPath' in request_data:
                filepath_inp = request_data['InPath']
                logging.debug('IDP-PRE-PROCESS : preprocesspdf :  contract_pdf_preprocess : Received filepath_inp : ' + filepath_inp)

        if filepath_inp is None:
            return jsonify(
                    message="Input Path is not provided",
                    category="error",
                    status=400)

    except Exception as ex:
        logging.error('IDP-PRE-PROCESS : preprocesspdf :  contract_pdf_preprocess : Unexpected Error in pdf preprocessing: ' + str(ex))
        return jsonify(
                    message="Unexpected Error in contract_pdf_preprocess: " + str(ex),
                    category="error",
                    status=500)
    try: 
        auth_user = os.getenv('OSCP_ESI_USER')
        auth_password = os.getenv('OSCP_ESI_PASS')

        logging.info('IDP-PRE-PROCESS : preprocesspdf :  contract_pdf_preprocess : Username is ' +  auth_user )
        if auth_user is None:
            print("Unable to read username", sys.exc_info()[0])
            return jsonify(
                    message="Unable to read username",
                    category="error",
                    status=500)

        if auth_password is None:
            print("Unable to read password", sys.exc_info()[0])
            return jsonify(
                    message="Unable to read password",
                    category="error",
                    status=500)

        allpdffiles  =  smbclient.listdir(filepath_inp,username=auth_user, password=auth_password)
        logging.info('IDP-PRE-PROCESS : preprocesspdf :  contract_pdf_preprocess : smbclient.open_all_files complete for :' + filepath_inp )

        opfilenames = []
        for files in allpdffiles:
            if files.upper().endswith('.PDF'):
                file = os.path.join(filepath_inp,files)
                try:
                    with smbclient.open_file(file, mode="rb",username=auth_user, password=auth_password) as fd:
                        logging.info('IDP-PRE-PROCESS : preprocesspdf :  contract_pdf_preprocess : smbclient.open_file complete for :' + filepath_inp )
                        bytesRead = fd.read()
                        logging.info('IDP-PRE-PROCESS : preprocesspdf :  contract_pdf_preprocess : read file complete for :' + filepath_inp )
                        fd.close()
                        full_doc = Pdf.open(BytesIO(bytesRead))
                        for page in full_doc.pages:
                            instructions = pikepdf.parse_content_stream(page)
                            data = pikepdf.unparse_content_stream(instructions)
                            decoded_data = data.decode("pdfdoc")
                            instruction_list = decoded_data.split("\n") # each instruction is separated by newline in decoded format

                            idx = 0
                            last_saved_state = ""
                            last_fill_state = ""
                            black_fill_state = "0 g"
                            while idx < len(instruction_list):
                                cur_instruction = instruction_list[idx]
                                if cur_instruction[len(cur_instruction)-2:] == "re":
                                    # table gridlines are thin rectangles, so don't change fill color if height
                                    # or width of rectangle operation are less than 3 (typical max gridline width)
                                    x, y, w, h = re.findall("[0-9]+(?:\.[0-9]+)?|\.[0-9]+", cur_instruction)
                                    if abs(float(w)) > 3 and abs(float(h)) > 3:
                                        if last_fill_state == "0 g" or "1 scn" in last_fill_state:
                                            if instruction_list[idx+1] == "f" or instruction_list[idx+1] == "f*":
                                                instruction_list.insert(idx, "1 g")
                                                instruction_list.insert(idx+3, last_fill_state)
                                                idx += 4
                                            else:
                                                idx += 1
                                        elif last_fill_state == "":
                                            if instruction_list[idx+1] == "f" or instruction_list[idx+1] == "f*":
                                                instruction_list.insert(idx, "1 g")
                                                instruction_list.insert(idx+3, black_fill_state)
                                                idx += 4
                                            else:
                                                idx += 1
                                        else:
                                            idx += 1
                                    else:
                                        idx += 1
                                elif cur_instruction == "0 g":
                                    last_fill_state = cur_instruction
                                    idx += 1
                                elif cur_instruction == "1 g":
                                    last_fill_state = cur_instruction
                                    idx += 1
                                elif cur_instruction[len(cur_instruction)-2:] == "rg":
                                    last_fill_state = cur_instruction
                                    idx += 1
                                elif cur_instruction == "1 scn":
                                    last_fill_state = "/Cs8 cs\n1 scn"
                                    idx += 1
                                elif cur_instruction == "0 scn":
                                    last_fill_state = "/Cs8 cs\n0 scn"
                                    idx += 1
                                elif cur_instruction[-1] == "k":
                                    last_fill_state = cur_instruction
                                    idx += 1
                                elif cur_instruction == "q":
                                    # store most recent non-stroke color state in case it's brought back
                                    last_saved_state = last_fill_state
                                    idx += 1
                                elif cur_instruction == "Q":
                                    # bring back last saved non-stroke color state
                                    last_fill_state = last_saved_state
                                    idx += 1
                                else:
                                    idx += 1 

                                    cleaned_decoded_data = "\n".join(instruction_list)
                                    page.Contents = full_doc.make_stream(cleaned_decoded_data.encode())

                        outputfilename = 'Cleansed_'+ files
                        outputfilepath = os.path.join(filepath_inp,outputfilename)
                        with smbclient.open_file(outputfilepath, mode="wb") as fd:
                            full_doc.save(fd)
                        opfilenames.append(outputfilename)

                except Exception as ex:
                    logging.error('IDP-PRE-PROCESS : preprocesspdf :  contract_pdf_preprocess : Unexpected Error in contract_pdf_preprocess: ' + str(ex))
                    return jsonify(
                        message="Unexpected Error in contract_pdf_preprocess: " + str(ex),
                        category="error",
                        status=420)
              
        return jsonify(
                   message="PDF Preprocess Completed",
                   category="Success",
                   outputFiles = opfilenames,
                   status=200)
        
    except Exception as ex:
        logging.error('IDP-PRE-PROCESS : preprocesspdf :  contract_pdf_preprocess : Unexpected Error in contract_pdf_preprocess: ' + str(ex))
        return jsonify(
                    message="Unexpected Error in contract_pdf_preprocess: " + str(ex),
                    category="error",
                    status=420)
            

