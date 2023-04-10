import os
import glob
import numpy as np
import pandas as pd
import datetime
import dateutil.parser
import dateparser
from dateutil.relativedelta import relativedelta
import re
import json
import math
import jaro
from collections import Counter
import difflib


def load_json(file_number):
    with open("my_pdfs\\"+str(file_number)+'.json', 'r') as f:
        myjson = json.load(f)
    return myjson


def polar_rotate_on_origin(point, page_angle):
    px, py = point
    px += 0.0000001 ## to ensure tan theta does not go to infinity
    theta = round(math.atan(py/px),2)
    del_theta = -(math.radians(page_angle))
    new_theta = theta+del_theta
    rx = math.sqrt(px**2 + py**2)
    # print("Distance from origin: " + str(rx))
    new_px = rx*math.cos(new_theta)
    new_py = rx*math.sin(new_theta)
    return (new_px,new_py)


def rotation_correction(bbox, page_angle, h, w):
    ## Now let's compute the translation correction by quadrant
    del_theta = -(page_angle)
#     print("Del_theta: " + str(del_theta))
    if -90<=del_theta<=0:
#         print("Case 3: del_theta betweeen (-90,0]")
        phi = abs(math.radians(del_theta))
        del_x = 0
        del_y = w*math.sin(phi)
    elif 90<del_theta<=180:
#         print("Case 2: del_theta betweeen (90,180]")
        phi = math.radians(abs(del_theta)-90)
        del_x = h*math.sin(phi)
        del_y = (h*math.cos(phi)) + (w*math.sin(phi))
        
    elif 0<=del_theta<=90:
#         print("Case 1: del_theta betweeen [0,90]")
        phi = abs(math.radians(del_theta))
        del_x = h*math.sin(phi)
        del_y = 0
        
    else:
#         print("Case 4: del_theta betweeen [-180,-90]")
        phi = math.radians(180-abs(del_theta))
        del_x = w*math.cos(phi)
        del_y = (h*math.cos(phi)) + (w*math.sin(phi))
#     print("Del_x: " + str(del_x))
#     print("Del_y: " + str(del_y))   
    rect_bb = np.reshape(bbox, (4,2))
    new_bb = []
    for corner in rect_bb:
#         print("Corner: " + str(corner))
        rotation_corrected = polar_rotate_on_origin(corner, page_angle)
        r_px = round(rotation_corrected[0],3)
        r_py = round(rotation_corrected[1],3)
        final_x , final_y = r_px + del_x , r_py + del_y
        new_bb.append(final_x)
        new_bb.append(final_y)
    
#         print("Final Corrected x: " + str(final_x))
#         print("Final Corrected y: " + str(final_y))
    return new_bb


def serialize_json(myjson):
    serialized_json = []
    try: 
        page_list = myjson["ocrStep"]["result"][0]["analyzeResult"]["readResults"]
        #print("First format found")
    except:
        page_list = myjson["OCRStep"]["Result"][0]["analyzeResult"]["readResults"]
    meta_data = []
    for page_index,page in enumerate(page_list):
        angle = page['angle']
        page_num = page_index+1
        height = page["height"]
        width = page["width"]
        meta_dict = {"page" : page_num,
                    "height" : height,
                    "width" : width,
                    "angle" : angle}
        meta_data.append(meta_dict)
        for line_index,line in enumerate(page["lines"]):
            line_num = line_index+1
            for word_in, word in enumerate(line["words"]):
                ##print("Word: " + str(word))
                bbox_ = word["boundingBox"]
                ## correcting for page rotation
                bbox_ = rotation_correction(bbox_, angle, height, width)
                ## Computing centroids
                rect_bbox = np.reshape(np.asarray(bbox_),(4,2))
                x_center = np.mean(rect_bbox,axis=0)[0]
                y_center = np.mean(rect_bbox,axis=0)[1]
                # #Rotate x_center and y_center
                # x_center, y_center = rotate((0,0), (x_center, y_center), math.radians(round(angle)))
                word_num = word_in+1
                word_dict = {"page": page_num, 
                             "line_num": line_num, 
                             "word_num" : word_num, 
                             "text" : word["text"],
                             "x_center" : x_center,
                             "y_center" : y_center,
                             "bbox": bbox_,
                            "confidence" : word["confidence"],
                            "status" : "Active"} ## Active, Inactive, Superactive
                serialized_json.append(word_dict)
    return serialized_json, meta_data


def find_window_width(serialized_json):
    ## Computing a Window Width with all words in serialized JSON
    height_list = []
    for word in serialized_json:
        bbox = word["bbox"]
        if word["text"].isdigit():
            height = abs(bbox[1] - bbox[7])
            height_list.append(height)
    try:
        mean = sum(height_list)/len(height_list)
        return mean * 1.1, serialized_json ## making window slightly wider than the average font height
    except:
        return 0 , serialized_json
    

def window_search_using_serialized_JSON(serialized_json, meta_data): #meta data contains page height and widths
    ## Computing a Window Width with all words in serialized JSON
    window_width, serialized_json = find_window_width(serialized_json)
    if window_width == 0:
        return []
    else:
        ## Using meta data to find number of windows in each page
        total_window = 0
        for page in meta_data:
            h = page["height"]
            w = page["width"]
            #print("Original Height and Width: " + str(h)+"  "+str(w))
            page_angle = page["angle"]
            del_theta = math.radians(abs(page_angle))
            new_h = round((h*math.cos(del_theta)) + (w*math.sin(del_theta)),2)
            new_w = round((h*math.sin(del_theta)) + (w*math.cos(del_theta)),2)
            print("Corrected Height and Width: " + str(new_h)+"  "+str(new_w)+" Page Angle: " + str(page_angle))
            num_windows = math.ceil(new_h/window_width)
            page["window_count"] = num_windows
            total_window += num_windows
        ## Windows below simply enumerates all windows starting at 0
        windows = list(range(total_window))
        ## Computing a word-->to--->window mapping list
        word_window_mapping = []
        for word in serialized_json:
            if word["status"] != "inActive":
                text = word["text"]
                bbox = word["bbox"]
                y_center = word["y_center"]
                page = word["page"]
                confidence = word["confidence"]
                ## Lets compute how many total windows in preceding windows starting at 0
                prev_page_windows = sum([x["window_count"] for x in meta_data if x["page"] < page]) - 1
                ## Lets now find window number for word on current page
                window_count_on_current_page = math.ceil(y_center/window_width) 
                ## Document level window_number starting at 0
                if prev_page_windows > 0:
                    window_number = prev_page_windows + window_count_on_current_page
                else:
                    window_number = window_count_on_current_page - 1
                ## Creating the temp_dict
                temp_dict = {"window" : window_number,
                            "word" : word}
                word_window_mapping.append(temp_dict)
            else:
                continue
        ## Let's finally compute the window_wise wordlist for final output using the mapping
        window_wise_list = []
        ## defaulting to start on page 1
        current_page = 1
        for window in windows:
            word_list = [x["word"] for x in word_window_mapping if x["window"] == window]
            window_wise_list.append(word_list)
    return window_wise_list


def get_dcm_with_fuzzy(window_wise_list):
    spl_char = '[@_!#$%^&*()<>?/\|}{~:]'
    ideal_string = 'DCMDCMDCMDCMDCMDCMDCMDCMMCDMCDMCDMCDMCDMCDMCDMCD'
    matched = {}
    for i, window in enumerate(window_wise_list):
        window_text = []
        for word in window:
            text = word["text"]
            text = "".join([c for c in text if c not in spl_char])
            window_text.append(text)
        window_text = "".join(window_text)
        match_score = round(jaro.jaro_winkler_metric(window_text, ideal_string), 3)
        if match_score >= 0.7:
            matched[i] = match_score
    if len(matched) == 0:
        return dict(), 0, window_wise_list, (0, 0), None
    max_match = 0
    max_key = None
    for key, value in matched.items():
        if value> max_match:
            max_match = value
            max_key = key
    left_x, right_x = 50, 0
    for word in window_wise_list[max_key]:
        text = word["text"]
        text = "".join([c for c in text if c not in spl_char])
        mcd_score = round(jaro.jaro_winkler_metric(text, 'MCD'), 3)
        dcm_score = round(jaro.jaro_winkler_metric(text, 'DCM'), 3)
        if max([mcd_score, dcm_score]) >= 0.7:
            if word['bbox'][0] < left_x:
                left_x = word['bbox'][0]
            if word['bbox'][2] > right_x:
                right_x = word['bbox'][2]
    col_width = (right_x - left_x)/16
    col_extent = {}
    for i in range(1,17):
        left = left_x + (i-1)*col_width
        right = left + col_width
        col_extent[i]=(left,right)
    perio_page = window_wise_list[max_key][0]["page"]
    return col_extent, col_width, window_wise_list, (left_x, right_x), perio_page


def find_tooth_window_and_deactivate(window_wise_list):
    tooth_list_1 = dict()
    tooth_list_2 = dict()
    perio_page = None
    spl_char = '[@_!#$%^&*()<>?/\|}{~:]'
    best_tooth_window = []
    found_1 = False
    found_2 = False
    for i,window in enumerate(window_wise_list):
        ideal_list_1 = list(range(1,17))
        l2 = list(range(17,33))
        ideal_list_2 = list(reversed(l2))
        word_text_list_1 = [] ## all integers between 1 and 16
        word_text_list_2 = [] ## all integers between 32 and 17
        for j,word in enumerate(window):
            try:
                ## remove special chars
                # if word["status"] not in ["max_date"]:
                #word["text"] = "".join([c for c in word["text"] if c not in spl_char])
                word_text = "".join([c for c in word["text"] if c not in spl_char])
                my_int = int(word_text)
                if 1<=my_int<=16:
                    word_text_list_1.append(my_int)
                elif 17<=my_int<=32:
                    word_text_list_2.append(my_int)
                else:
                    pass
            except:
                pass
        ## Computing probability of being tooth_window_1
        sm_1=difflib.SequenceMatcher(None,word_text_list_1,ideal_list_1)
        ##print("Window: " + str(i)+"--------------Text List: " + str(word_text_list_1))
        confidence_1 = sm_1.ratio()
        ## Computing probability of being tooth_window_2
        sm_2=difflib.SequenceMatcher(None,word_text_list_2,ideal_list_2)
        ##print("Window: " + str(i)+"--------------Text List: " + str(word_text_list_2))
        confidence_2 = sm_2.ratio()
        if  confidence_1 > 0.85  and confidence_1 > confidence_2 and not found_1 == "Completed":
            found_1 = "Completed"
            for j, word in enumerate(window):
                word["status"] = "inActive"
                text = word['text']
                perio_page = word['page']
                x_center = word['x_center']
                y_center = word['y_center']
                try:
                    text = "".join([c for c in text if c not in spl_char])
                    text = int(text)
                    if text in range(1,17):
                        #print("Found a tooth at x_center : " + str(x_center) +    "   Word_text: " + str(text) )
                        tooth_list_1[text] = x_center
                except ValueError:
                    continue
            # print("We have found a tooth window - (1-16) at Window Number: " + str(i))
        elif confidence_2 > 0.85  and not found_2 == "Completed":
            # print("We have found a tooth window - (17-32) at Window Number: " + str(i))      
            found_2 = "Completed"
            for j, word in enumerate(window):
                word["status"] = "inActive"
                text = word['text']
                perio_page = word['page']
                x_center = word['x_center']
                y_center = word['y_center']
                try:
                    text = "".join([c for c in text if c not in spl_char])
                    text = int(text)
                    if text in range(17,33):
                        tooth_list_2[33-text] = x_center
                except ValueError:
                    continue
    if len(tooth_list_1.keys()) > len(tooth_list_2.keys()):
        # print("Found tooth window 1")
        return found_1, tooth_list_1, window_wise_list, perio_page
    else:
        # print("Found tooth window 2")
        return found_2, tooth_list_2, window_wise_list, perio_page
        

def complete_tooth_puzzle(tooth_list,found):
    all_tooth_pos = dict()
    #import pdb; pdb.set_trace()
    if found == "Completed":
        all_tooth_extents = dict()
        tooth_found_list = list(tooth_list.keys())
        ## Let's prepopulate the final_dict
        dist_list = []
        last_tooth = tooth_found_list[0]
        for i,tooth in enumerate(tooth_found_list):
            if i==0:
                pass
            else:
                ## check if tooth is consequtive to last tooth
                if tooth-last_tooth==1:
                    sample_width = tooth_list[tooth]-tooth_list[last_tooth]
                    dist_list.append(sample_width)
                    last_tooth=tooth
            all_tooth_pos[tooth] = tooth_list[tooth]
        try:
            col_width = sum(dist_list)/len(dist_list)
        except:
            print("Column Width Not Found")
            return all_tooth_extents, None
        ## lets now solve and add for missing teeth
        missing_teeth = [i for i in range(1,17) if i not in tooth_list.keys()]
        ## Solving for the case with missing teeth first
        if len(missing_teeth)>0:
            ##print("Missing Teeth: " + str(missing_teeth))
            for missing_tooth in missing_teeth:
                ## check if anything left, by counting backwords to 1
                try:
                    left_neighbor = max([tooth for tooth in tooth_list.keys() if tooth < missing_tooth])
                except:
                    left_neighbor = False
                try:
                    right_neighbor = min([tooth for tooth in tooth_list.keys() if tooth > missing_tooth])
                except:
                    right_neighbor = False
                ##print("Missing_Tooth: "+str(missing_tooth)+" Left Neighbor: " + str(left_neighbor) + " Right Neighbor: "+str(right_neighbor))
                if not left_neighbor:
                    n_gaps_right = right_neighbor - missing_tooth
                    missing_tooth_pos = tooth_list[right_neighbor]-(n_gaps_right*col_width)
                    all_tooth_pos[missing_tooth] = missing_tooth_pos
                elif not right_neighbor:
                    n_gaps_left = missing_tooth - left_neighbor
                    missing_tooth_pos = tooth_list[left_neighbor]+(n_gaps_left*col_width)
                    all_tooth_pos[missing_tooth] = missing_tooth_pos
                else:
                    n_gaps_left = missing_tooth - left_neighbor
                    n_gaps_right = right_neighbor - missing_tooth
                    l_pos = tooth_list[left_neighbor]
                    r_pos = tooth_list[right_neighbor]
                    missing_tooth_pos=((l_pos*n_gaps_right)+(r_pos*n_gaps_left))/(n_gaps_left+n_gaps_right)
                    all_tooth_pos[missing_tooth] = missing_tooth_pos
        myKeys = list(all_tooth_pos.keys())
        myKeys.sort()
        all_tooth_pos_sorted = {i: all_tooth_pos[i] for i in myKeys}
        return all_tooth_pos_sorted, col_width
        
    else:
        return all_tooth_pos , None
    

def find_column_extents(all_tooth_pos, column_width):
    column_extents = dict()
    left_end, right_end = (0,0)
    for key, value in all_tooth_pos.items():
        left_x = value - (0.5 * column_width)
        right_x = value + (0.5 * column_width)
        if key == 1:
            left_end = left_x
        elif key == 16:
            right_end = right_x
        column_extents[key] = (left_x, right_x)
    return column_extents, (left_end, right_end)   


def isolate_perio_page(window_wise_list, perio_page):
    if perio_page is not None:
        for i, window in enumerate(window_wise_list):
            for word in window:
                if word['page'] != perio_page:
                    word['status'] = 'inActive'
    return window_wise_list


def superactivate_keyword_windows(windowwise_word_lists):
    good_list = ["pd", "probing depth", "pocket", "probing" , "depth", "pckt", "pck", "pkt"]
    bad_list = ["gm","cal","mgj","fg","tooth","ling","gingival", "margin", "clinical", "attachment" , "clinical attachment", "cal", "" ]
    good_words_list = []
    for window in windowwise_word_lists:
        for word in window:
            if word['status'] != 'inActive':
                good_sim = max([jaro.jaro_winkler_metric(word["text"].lower(),good_word) for good_word in good_list])
                bad_sim = max([jaro.jaro_winkler_metric(word["text"].lower(),bad_word) for bad_word in bad_list])
                if good_sim >=0.8:
                    word["status"] = "good_word"
                    good_words_list.append(word)
                elif  bad_sim >=0.8:
                    word["status"] = "bad_word"
    ## Clustering the good_words on x_center
    cluster = []
    #good_words_x_center = [word['x_center'] for word in good_word_list]
    sorted_good_words_list = sorted(good_words_list, key=lambda d: d['x_center'])
    last_x_center = None
    cluster_list = list()
    temp_list = list()
    for word in sorted_good_words_list:
        x_center = word["x_center"]
        if last_x_center is None:
            last_x_center = x_center
            temp_list.append(word)
        elif (x_center - last_x_center) < 1:
            temp_list.append(word)
        else:
            cluster_list.append(temp_list)
            temp_list = []
    cluster_length_list = [len(item) for item in cluster_list]
    idx_max = cluster_length_list.index(max(cluster_length_list))
    cluster_list.pop(idx_max)
    for item in cluster_list:
        for word in item:
            page = word['page']
            line = word['line_num']
            word_num = word['word_num']
            for window in windowwise_word_lists:
                for window_word in window:
                    if window_word['page_num'] == page and window_word['line_num'] == line and window_word['word_num'] == word_num:
                        window_word['status'] = 'inActive'
    return windowwise_word_lists


def get_dates(windowwise_word_list):
    dateRegExp_ = [
            "\d{2}[-/]\d{2}[-/]\d{4}", '\d{1}[-/]\d{2}[-/]\d{4}', '\d{1}[-/]\d{1}[-/]\d{4}',
            '\d{1}[-/]\d{1}[-/]\d{4}', '\d{1}[-/]\d{1}[-/]\d{3}', '\d{4}[-/]\d{2}[-/]\d{2}',
            '\d{2}[-/]\d{2}[-/]\d{2}','\d{4}[-/:]\d{2}[-/:]\d{2}','\d{2}[-/:]\d{2}[-/:]\d{2}'
            '\d{2}[-/]\w{3}[-/]\d{2}', '\d{2}[-/]\w{3}[-/]\d{4}', '\d{4}[-/]\w{3}[-/]\d{2}',
            '\w{3}\s\d{2}[,]\s\d{4}', '\w{3}\s\d{2}[.]\s\d{4}', '\w{3}\s\d{2}[,]\s\d+',
            '\w{3}\s\d{2}[.]\s\d+', '\w+\s\d{2}[.]\d{4}', '\w+\s\d{2}[,]\d{4}', '\w+\s\d{2}[,]\s\d{4}',
            '\w+\s\d{2}[.]\s\d{4}', '\d{1}[-/]\d{1}\s\d{1}[-/]\d{4}', '\w+\s\d{2}[.]\s\d{4}',
            '\w+\s\d{2}[.]\s\w{4}', '\w+\s\d{2}[.]\s\d{4}', '\w+\s\d+[,]\s\d+', '\w+\s\d+[.]\s\d+',
            '([a-zA-Z0-9]{3,9}[-/.,\\s]{1,3}[a-zA-Z0-9]{1,3}[-/.,\\s]{1,2}[a-zA-Z0-9]{2,4})',
                  ]
    patterns = [re.compile(i) for i in dateRegExp_]
    dates = list()
    for window in windowwise_word_list:
        for word in window:
            text = word['text']
            for p in patterns:
                match = p.search(text)
                if match and word['status']!='inActive' and word['status']!='superActive':
                    dates.append(word)
                    word['status'] = "superActive"        
    if len(dates)>0:
        for dict_ in dates:
            date_ = dateparser.parse(dict_['text'])
            dict_['date'] = date_
        
        return pd.DataFrame(dates), windowwise_word_list
    else:
        return None, windowwise_word_list


def get_max_date(data):
    try:
        if data.shape[0]>=1:
            data['count'] = data.groupby('date')['date'].transform('count')
            df = data[data['count']==4]
            return df.date.max()
    except AttributeError:
        return None
    

def status_correction_for_dates(df, max_date, window_wise_list):
    try:
        df['status'] = df.apply(lambda x: x['status'] if max_date == x['date'] else 'inActive', axis=1)
        for window in window_wise_list:
            for word in window:
                if word['status'] == 'superActive':
                    if len(df[(df['page']==word['page']) & (df['line_num']==word['line_num']) & (df['word_num']==word['word_num']) & (df['date']==max_date)])>0:
                        word['status'] = 'max_date'
                    else:
                        word['status']='inActive'
    except:
        pass
    return window_wise_list


def deactivate_alphabetes_only(window_wise_list):
    for window in window_wise_list:
        for word in window:
            if word["status"] == 'Active':
                if word["text"].isalpha():
                    word["status"] = 'inActive'
    return window_wise_list


def remove_left_right_words(end_extents, window_wise_list):
    left_end = end_extents[0]
    right_end = end_extents[1]
    left_end = -50
    right_end = 50
    for window in window_wise_list:
        for word in window:
            if word["status"] not in ["superActive", "bad_word", "good_word", "max_date"]:
                if word["bbox"][2] < left_end or word["bbox"][0] > right_end:
                    word["status"] = "inActive"
                else:
                    pass
            else:
                pass
    return window_wise_list


def create_activated_serialized_json(window_wise_list):
    activated_serialized_json = list()
    for window in window_wise_list:
        for word in window:
            if word["status"] != 'inActive':
                activated_serialized_json.append(word)
    return activated_serialized_json


def find_top_4_row(windowwise_word_lists):
    spl_char = re.compile('[@_!#$%^&*()<>?/\|}{~:]')
    good_list = ["pd", "probing depth", "pocket", "probing" , "depth", "pckt", "pck", "pkt"]
    bad_list = ["gm","cal","mgj","fg","tooth","ling","","gingival", "margin", "clinical", "attachment" , "clinical attachment", "cal", "" ]
    confidence_list = []
    for window_list in windowwise_word_lists:
        good_ratios = [0]
        bad_ratios = [0]
        n_digits = 0
        n_alpha = 0
        max_date = 0
        
        ## Computing the Probability of Good Word
        for word in window_list:
            if word["status"] != "inActive":
                if word['status'] in ["good_word", "bad_word"]:
                    good_sim = max([jaro.jaro_winkler_metric(word["text"].lower(),good_word) for good_word in good_list])
                    bad_sim = max([jaro.jaro_winkler_metric(word["text"].lower(),bad_word) for bad_word in bad_list])
                    good_ratios.append(good_sim)
                    bad_ratios.append(bad_sim)
                if (spl_char.search(word["text"]) == None):
                    n_digits += sum(c.isdigit() for c in word["text"] if c != '0')
                else:
                    n_digits += 0
                n_alpha +=  sum(c.isalpha() or c=='0' for c in word["text"])
                if word['status'] == 'max_date':
                    max_date += 1
            else:
                pass
            
        if max(good_ratios)<=0.8:
            good_keyword_metric = 0
        else:
            good_keyword_metric = 1
        if max(bad_ratios)<=0.8:
            bad_keyword_metric = 0
        else:
            bad_keyword_metric = 1
        if n_digits < 12:
            confidence = 0.01
        else:
            confidence = 0.8 * (good_keyword_metric) - 2.0 *(bad_keyword_metric) + 0.8*(n_digits/(n_digits+n_alpha)) + 0.8*(n_digits/48) + 0.8*max_date
        confidence_list.append(confidence)
    top_4_idx = np.argsort(confidence_list)[-4:]
    top_4_idx = sorted(top_4_idx)
    top_4_values = [confidence_list[i] for i in top_4_idx]
    new_list = []
    for index in top_4_idx:
        new_list.append(windowwise_word_lists[index])
    return new_list, top_4_idx 


def tooth_char_mapping_from_top_4(list_of_top_4_windows, sample_tooth_extents):
    tooth_char_mapping_list = []

    for row_index,row in enumerate(list_of_top_4_windows):
        for word in row:
            bbox = word["bbox"]
            text = word["text"]
            char_list = [x for x in text]
            ## print("-----------------------------Character List-------------: " + str(char_list))
            bbox_width = abs(bbox[2] - bbox[0])
            bbox_left_x = bbox[0]
            if len(char_list)>=1:
                char_width = bbox_width/len(char_list)
            else:
                char_width = 0
            ##print("Character Width: " + str(char_width))
            for c_index,c in enumerate(char_list):
                char_x_center = bbox_left_x + (char_width/2) + (c_index * char_width)
                ##print("Character: " + str(c)+ " Has Center: " + str(char_x_center))
                ## Checking if character is a digit
                if c.isdigit():
                    ## print("Digital Character Found: " + str(c))
                    ## Now we will loop through out column extents to find the distance of character from each col center
                    for key, value in sample_tooth_extents.items():
                        left_x = round(value[0],5)
                        right_x = round(value[1],5)
                        tooth_col_num = key
                        col_center = (left_x + right_x)/2
                        ##dist = abs(char_x_center - col_center)
                        if left_x < char_x_center <= right_x: ## dist <= (0.55 * avg_col_width) and ## To ensure the character is close enough to the tooth col center
                            ## Based on row_index, let's set the character to a given tooth
                            if row_index == 0 or row_index == 1: ## Dealing with row_1 and row_2
                                my_tooth_found = tooth_col_num

                                temp_dict = {"tooth_num" : my_tooth_found,
                                            "char" : c}
                                ## print("Found a Pair: " + str(temp_dict))
                                tooth_char_mapping_list.append(temp_dict)
                            if row_index == 2 or row_index == 3: ## Dealing with row_3 and row_4
                                my_tooth_found = 33 - tooth_col_num

                                temp_dict = {"tooth_num" : my_tooth_found,
                                            "char" : c}
                                ## print("Found a Pair: " + str(temp_dict))
                                tooth_char_mapping_list.append(temp_dict)
    return tooth_char_mapping_list


def final_tooth_char_mapping(tooth_char_mapping_list):
    all_teeth_char_list = []
    for tooth in range(1,33):
        tooth_char_list = []
        for map_dict in tooth_char_mapping_list:
            if map_dict["tooth_num"] == tooth:
                tooth_char_list.append(map_dict["char"])
        all_teeth_char_list.append({"tooth" : tooth,
                                   "char_list" : tooth_char_list})
    return all_teeth_char_list
