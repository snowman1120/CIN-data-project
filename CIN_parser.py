# Description:
# This script defines the Document and Page classes to streamline the flow of information through the script.

from cmath import tan
import os, sys, traceback
import logging
import statistics
import numpy as np
from io import BytesIO
import cv2
import fitz
import pytesseract
from pytesseract import Output
import re   
import scipy.ndimage
from PIL import Image
from CIN_post_proc import post_processing
from pdf2image import convert_from_path
Image.MAX_IMAGE_PIXELS = 1000000000 
# Record
logger = logging.getLogger('parse_table')
logger.setLevel(logging.DEBUG)
# Global variables
medi_val = [40, 20]
index = []
head_cols = []
digit_zoom = 1
page_hor_ths = 70 
# page_digit = False
# class
class Document:
    def __init__(self, img_name, doc_dir, output_dir):
        # Initialize key attributes and filepaths
        self.img_name = img_name
        self.doc_name = '.'.join(img_name.split('.')[:-1])
        if self.doc_name == '':
            self.doc_name = img_name
        self.doc_dir = doc_dir
        self.output_dir = output_dir
        self.pages = []
        self.output_dir = os.path.join(self.output_dir, re.sub('[.\\/:*?"<>|]', '', self.doc_name))
        self.output_dir = self.output_dir.strip()
        self.digit_doc = None
        global digit_zoom
        digit_zoom = 1
        self.head_check = False
        os.mkdir(self.output_dir)
    def pil_to_cv2(self, image):
        open_cv_image = np.array(image)
        return open_cv_image[:, :, ::-1].copy() 

    def split_pages(self):
        '''
        1. Splits the input pdf into pages
        2. Writes a temporary image for each page to a byte buffer
        3. Loads the image as a numpy array using cv2.imread()
        4. Appends the page image/array to self.pages

        Notes:
        PyMuPDF's get_pixmap() has a default output of 96dpi, while the desired
        resolution is 300dpi, hence the zoom factor of 300/96 = 3.125 ~ 3.
        '''
        if (self.img_name.split('.')[-1]).lower() == 'pdf':  
            logger.debug("Splitting PDF into pages")
            pdf_full_name = os.path.join(self.doc_dir, self.doc_name + ".pdf")
            self.digit_doc = fitz.open(pdf_full_name)
            try:
                pdf_max_len = 0
                for page in self.digit_doc:
                    if pdf_max_len < max(page.mediabox_size): pdf_max_len = max(page.mediabox_size)
                temp = self.digit_doc[0]
                if temp.rotation == 90 or temp.rotation == 270:
                    pdf_hei, pdf_wid = self.digit_doc[0].mediabox_size
                else :
                    pdf_wid, pdf_hei = self.digit_doc[0].mediabox_size             
                dpi, pdf_lim, img_lim = 280, 1200, 4000
                if pdf_max_len/72*dpi > img_lim:
                    dpi = int(img_lim/pdf_max_len*72)
                imgpages = convert_from_path(pdf_full_name, dpi, poppler_path = r"C:/Program Files/poppler-22.04.0/Library/bin")
                img_hei, img_wid = imgpages[0].height, imgpages[0].width
                if pdf_max_len > pdf_lim:
                    global digit_zoom
                    digit_zoom = pdf_lim/pdf_max_len
                    pdf_hei, pdf_wid = pdf_hei*digit_zoom, pdf_wid*digit_zoom
                for i, page in enumerate(imgpages):
                    page_img = self.pil_to_cv2(page)
                    page_img = cv2.resize(page_img, None, fx=3*pdf_wid/img_wid, fy=3*pdf_hei/img_hei)  
                    self.pages.append(page_img)
            except:
                pass
        else:
            page_img = cv2.imread(os.path.join(self.doc_dir, self.img_name))
            self.pages.append(page_img)
        if len(self.pages) == 0:
            val = "01"
        else:
            val = None
        return val

    def parse_doc(self):
        '''
        In a document, main process is done for all pages 
        '''
        # Split and convert pages to images
        error = self.split_pages()
        if error == "01":
            err = "PDF file is damaged"
        Box, Text = [], []
        page_num = 1

        for idx, img in enumerate(self.pages):
            try:
                if idx <3:
                    logger.debug(f"Reading page {idx + 1} out of {len(self.pages)}")
                    page = Page(img, page_num, self.img_name, self.output_dir, self.head_check, self.digit_doc[idx])
                    box, text = page.parse_page()
                    if len(text) > 0:
                        page_num = page_num + 1
                        Box.append(box)
                        Text.append(text) 
                        self.head_check = True

            except Exception as e:
                if str(e) == "02":## when heading page is not existed in pdf.
                    error = str(e)
                    err = "Heading page is not existed (not high_y)"  
                    break
                elif str(e) == "03":## Style of table is violated
                    err = "Error in getting index"
                    error = str(e)
                    break
                elif str(e) == "04":## recognition of sub title is not exact in head page
                    error = str(e)
                    err = "Error in checking index."
                    break
                elif str(e) == "06": ## When lines is not existed in firstpage.
                    err = f"Borders is not exact in page {str(idx+1)}"
                    error = str(e)
                elif str(e) == "07":## When preprocessing is poor.
                    error = str(e)
                    err = "Warning in preprocessing...Please ask to developer"
                elif str(e) == "08":## When preprocessing is poor.
                    error = str(e)
                    err = "Text is not existed in table...Please check current page" 
                else:
                    error = "99"
                    err = f"Program runtime Error page {str(idx+1)}"
                    _, _, exc_tb = sys.exc_info()
                    print("     Error=%s,\n     File=%s,\n     L=%s\n" % (str(e), traceback.extract_tb(exc_tb)[-1][0], traceback.extract_tb(exc_tb)[-1][1]))
                    break
                ### For warning ###
                logger.info(f"    Warning IN Page {str(idx+1)} of {self.doc_name}: {err}")
                logger.info(f"    Page {str(idx+1)} of {self.doc_name} ran into warning(some errors) in while parsing. ***Warning:{error}***")

        if len(Text) == 0:
            error = "05"
            err = "All pages hasn't border or text"
        else:
            try:
                if len(Text) > 0:
                    save_path = os.path.join(self.output_dir,'_'.join((self.img_name, ".xlsx")))
                    post_processing([[Box, index]], [Text], save_path, [self.img_name])
            except:
                pass

        if error is None or (int(error)>5 and int(error) != 99):
            logger.info(f"    Completed parsing {self.doc_name} with no errors, ...........OK")
            return [Box, index], Text
        else:
            logger.info(f"    ERROR IN {self.doc_name}: {err}")
            logger.info(f"    {self.doc_name} can't be run. ***Error:{error}***, ............failed")
            try:
                os.rmdir(self.output_dir)
            except:
                pass
            return error, None, None

class Page:
    def __init__(self, img, page_num, img_name, output_dir, headers_checking, digit_page):
        self.img = img
        self.page_num = page_num
        self.doc_name = '.'.join(img_name.split('.')[:-1])
        if self.doc_name == '':
            self.doc_name = img_name
        self.img_name = '_'.join((self.doc_name,str(self.page_num)))#, str(img_name[-4:])))
        self.output_dir = output_dir
        self.headpage_checking = headers_checking
        self.rows = []
        self.cols = []
        self.table = None
        self.tk = 3 # considering half of border thickness
        self.ths = 200
        self.lim = [25, 16] # under limit of w and h    
        self.digit_page = digit_page
        self.digit_cen_value = []
        self.digit_value = []
    
    def set_image_dpi(self, file_path):
        im = Image.open(file_path)
        # size = self.get_size_of_scaled_image(im)
        # im_resized = im.resize(size, Image.ANTIALIAS)
        im.save(file_path, dpi=(300, 300))  # best for OCR
    def line_detector(self,image, prop):
        # Convert color image to grayscale
        img = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        # Binarize image using thresholding
        _, img = cv2.threshold(img, 128, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
        erode_size, dilate_size = 50, 5
        values = []
        if prop == 'hor':
            # ind = 0
            img = cv2.dilate(img, np.ones((1,dilate_size)), iterations=1)
            img = cv2.erode(img, np.ones((1,erode_size)), iterations=1)            
            cnt, _ = cv2.findContours(img, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        
            for c in cnt:
                x, y, w, h = cv2.boundingRect(c) 
                if w > 200 and h < 20:
                    values.append(int(y+h/2))            
        else: 
            # ind = 1
            img = cv2.dilate(img, np.ones((dilate_size, 1)), iterations=1)
            img = cv2.erode(img, np.ones((erode_size, 1)), iterations=1)  
            cnt, _ = cv2.findContours(img, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        
            for c in cnt:
                x, y, w, h = cv2.boundingRect(c) 
                if h > 200 and w < 20:
                    values.append(int(x+w/2))
        return values
    def deter_angle(self,image, prop):
        # Convert color image to grayscale
        img = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        # Binarize image using thresholding
        _, img = cv2.threshold(img, 128, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
        erode_size, dilate_size = 50, 5
        if prop == 'hor':
            # ind = 0
            img = cv2.dilate(img, np.ones((1,dilate_size)), iterations=1)
            img = cv2.erode(img, np.ones((1,erode_size)), iterations=1)            
            cnt, _ = cv2.findContours(img, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        else: 
            # ind = 1
            img = cv2.dilate(img, np.ones((dilate_size, 1)), iterations=1)
            img = cv2.erode(img, np.ones((erode_size, 1)), iterations=1)  
            cnt, _ = cv2.findContours(img, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
            # self.ver = [[int(x[0][1]-(x[1][1]+erode_size)/2), int(x[0][1]+(x[1][1]+erode_size)/2)] for x in list(map(cv2.minAreaRect, cnt)) if x[1][ind]>200]
        angle_list = [x[-1] for x in list(map(cv2.minAreaRect, cnt)) \
            if abs(x[-1]) != 270 and abs(x[-1]) != 180 and (x[1][0]>200 or x[1][1]>200)]
        if len(angle_list) < 3:
            angle_list = [x[-1] for x in list(map(cv2.minAreaRect, cnt)) \
                    if abs(x[-1]) != 270 and abs(x[-1]) != 180 and (x[1][0]>100 or x[1][1]>100)]

        try:
            angle = statistics.median(angle_list)
        except statistics.StatisticsError:
            angle = 0
        if prop == "ver":
            if abs(angle) < 45: 
                verlines = [[int(x[0][1]-(x[1][1]+erode_size)/2), int(x[0][1]+(x[1][1]+erode_size)/2)] for x in list(map(cv2.minAreaRect, cnt)) if x[1][1]>200]
            else:
                verlines = [[int(x[0][0]-(x[1][0]+erode_size)/2), int(x[0][0]+(x[1][0]+erode_size)/2)] for x in list(map(cv2.minAreaRect, cnt)) if x[1][0]>200]

            if len(verlines) < 3: 
                raise Exception("06")
            else:
                verlines_y = np.array(verlines)
                self.min_y, self.max_y = self.min_max_y(verlines_y)

        if angle < -45:
            angle += 90
        elif angle > 45:
            angle -= 90
        return angle     
          
    def preprocess_image(self):
        '''
        1. Gets all angles of horizontral lines from function lines_extraction()
        2. All angles are in range of 80deg~100deg or -10deg~10deg. All angles are split into two sets. 
        3. Select one set with more frequently angles.
        4. Find out median value of selected set.
        5. Rotate image according to the valuel.
        '''

        file_path = "results/temp.jpg"
        cv2.imwrite(file_path, self.img)
        self.set_image_dpi(file_path)
        self.img = cv2.imread(file_path)

        angle = self.deter_angle(self.img, 'hor')

        (h, w) = self.img.shape[:2]
        center = (w // 2, h // 2)
        M = cv2.getRotationMatrix2D(center, angle, 1.0)
        self.img = cv2.warpAffine(self.img,
                             M,
                             (w, h),
                             flags=cv2.INTER_CUBIC,
                             borderMode=cv2.BORDER_REPLICATE)
        angle =self.deter_angle(self.img, 'ver')
        shift = np.tan(np.deg2rad(angle)) * h
        if shift < 0:
            srcTri = np.array( [[0, 0], [w+shift-1, 0], [0, h - 1]] ).astype(np.float32)
            dstTri = np.array( [[-shift, 0], [w-1, 0], [0, h-1]] ).astype(np.float32)        
        else:
            srcTri = np.array( [[shift, 0], [w-1, 0], [0, h - 1]] ).astype(np.float32)
            dstTri = np.array( [[0, 0], [w-shift-1, 0], [0, h-1]] ).astype(np.float32)                                
        warp_mat = cv2.getAffineTransform(srcTri, dstTri)
        self.img = cv2.warpAffine(self.img, warp_mat, (w, h))
        cv2.imwrite(file_path, self.img)
        self.img = cv2.imread(file_path)
        self.img_removedByline = self.line_remove(self.img)

        return self


    def check_scan_or_digit(self):
        '''
        Check if pdf is digital or scanned.
        '''
        d = self.digit_page.get_text_words()
        digit = False
        if len(d) > 10:# and digit_flag:
            digit = self.get_digit(d) 
        return digit

    def line_remove(self, image):
        result = image.copy()
        gray = cv2.cvtColor(image,cv2.COLOR_BGR2GRAY)
        thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]

        # Remove horizontal lines
        horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (40,1))
        remove_horizontal = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, horizontal_kernel, iterations=2)
        cnts = cv2.findContours(remove_horizontal, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cnts = cnts[0] if len(cnts) == 2 else cnts[1]
        for c in cnts:
            cv2.drawContours(result, [c], -1, (255,255,255), 5)

        # Remove vertical lines
        vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1,35))
        remove_vertical = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, vertical_kernel, iterations=2)
        cnts = cv2.findContours(remove_vertical, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cnts = cnts[0] if len(cnts) == 2 else cnts[1]
        for c in cnts:
            cv2.drawContours(result, [c], -1, (255,255,255), 5)

        return result
    def text_detection(self, digit):
        '''
        This function performs following:
        - finds heading(date, time, bench, court)
        - finds headcols(list including column locations of SR, CP, CI, PURPOSE, SECTION, NAME OF PARTIES, REMARK)
        - finds location of table in heading page
        '''
        img = self.img.copy()
        config = '--psm 11'
        temp_page_digit = True
        high_cen, temp_page_digit = self.get_headpage(self.img_removedByline, config, digit, temp_page_digit) # high_y, high_y2, high_cen: location of top, bottom, center in heading row
        
        if high_cen is None:
            digit = False
            high_cen, temp_page_digit = self.get_headpage(img, '--psm 6', digit, temp_page_digit)
            if high_cen is None:
                self.headpage_checking = False
            else:
                self.img = self.img[int(high_cen)-25:, :]
                self.img[0:1, :] = [0,0,0] 
                self.img_removedByline = self.img_removedByline[int(high_cen)-25:, :]
                self.headpage_checking = True                
        else:
            alpa = int(high_cen)-25
            if temp_page_digit:            
                text = self.modify_digit(alpa, 0)
            self.img = self.img[alpa:, :]
            self.img[0:1, :] = [0,0,0] 
            self.img_removedByline = self.img_removedByline[int(high_cen)-25:, :]
            self.headpage_checking = True
            self.min_y = 0
            self.max_y = self.max_y-alpa

        return temp_page_digit
      
    def getting_index(self, text, xc, index, flag):
        '''
        This function finds index from text.
        This function is called 2 times. So index is updated to improve the accuracy
        '''
        sl, cin, name, pan = flag
        ###
        # sub_wid_raito = np.array([315, 215, 215, 230, 500, 170])/2/2526 ## got on bais of a lot table, denotes center point ratio
        
        # ratio between centers of cp and ca is about 0.104. So we set 0.06 as under limit value, 0.2 as upper limit value
        ###
        # cp_ca_ratio = True if 0.06<(xc[cnt]-index[0])/self.img.shape[1]<0.2 else False
        
        for cnt, te in enumerate(text):
            te = te.lower()
            if ('sl' in te or te.strip() == 's.' or te.strip() == 's' or '.no' in te or te=='no') and sl:
                sl, index[0] =False, xc[cnt]
            if 'cin' in te and cin:
                cin, index[1] = False, xc[cnt]
            elif ("name" in te) and name:
                name, index[2] = False, xc[cnt]
            elif (te.strip() == "pan" or ("pan" in te and len(te)>9)) and pan:
                pan, index[3] = False, xc[cnt]

        # index[0] = 10000
                
        flag = [False, cin, name, pan]
        return index, flag   

    def getting_textdata(self, img, conf, zoom_fac, split_val):
        '''
        img: soucr image to process.
        conf: tesseract conf (--psm xx)
        zoom_fac: image resize factor.
        split_val: factor to consider for coordinate of texts when image is splited into two parts
        '''
        d = pytesseract.image_to_data(img, output_type=Output.DICT, config=conf)
        text_ori = d['text']
        left_coor, top_coor, wid, hei, conf = d['left'], d['top'], d['width'], d['height'], d['conf']        
        ### removing None element from text ###
        text, left, top, w, h, accu, xc, yc= [], [], [], [], [], [], [], []
        for cnt, te in enumerate(text_ori):
            if te.strip() != '' and wid[cnt] > 10 and hei[cnt] > 10:
                text.append(te)
                left.append(int((left_coor[cnt]+split_val)/zoom_fac))
                top.append(int(top_coor[cnt]/zoom_fac))
                w.append(int(wid[cnt]/zoom_fac))
                h.append(int(hei[cnt]/zoom_fac))
                accu.append(conf[cnt])    
                xc.append(int((left_coor[cnt]+wid[cnt]/2+split_val)/zoom_fac))
                yc.append(int((top_coor[cnt]+hei[cnt]/2)/zoom_fac))
        return text, left, top, w, h, accu, xc, yc

    def TextinRegion(self, x, y, ww, hh, xc, yc):
        range_y_inds = [i for i in range(len(xc)) if yc[i] > y and yc[i] < y+hh]
        range_x_inds = [i for i in range(len(xc)) if xc[i] > x and xc[i] < x+ww]
        range_inds = set(range_x_inds) & set(range_y_inds)     
        return range_inds

    def Index(self, img_text, zoom_fac):
        '''
        1. Resize img_text
        2. To improve accuracy, split img_text into two part
        3. First get all texts of splited image by --psm 6, and unity them
        4. If temp has -1, again get all texts of splited image by --psm 11 and unity them.
            At that time, the good result by --psm 6 is considered.
        5. Get finial temp (index)
        '''
        temp = [-1,-1,-1,-1]
        flag = [True, True, True, True]        
        
        img_text_resize = cv2.resize(img_text, None, fx=zoom_fac, fy=zoom_fac)  
        # split_val = int(verlines_x[split_ths] * zoom_fac)
        # img_text_1 = img_text_resize[:,0:split_val,:]
        # img_text_2 = img_text_resize[:, split_val:-1,:]
        
        text_, _, _, _, _, _, xc, _ = self.getting_textdata(img_text_resize, '--psm 6', zoom_fac, 0)
        # text_2, _, _, _, _, _, xc2, _ = self.getting_textdata(img_text_2, '--psm 6', zoom_fac, split_val)
        # text_, xc = text_1 + text_2, xc1+xc2
        xc, text_ = list(zip(*sorted(zip(xc, text_))))
        temp, flag = self.getting_index(text_, xc, temp, flag)

        if -1 in temp: 
            temp_text, _, _, _, _, _, temp_xc, _ = self.getting_textdata(img_text_resize, '--psm 11', zoom_fac, 0)
            # temp_text2, _, _, _, _, _, temp_xc2, _ = self.getting_textdata(img_text_2, '--psm 11', zoom_fac, split_val)
            # temp_text, temp_xc = temp_text1 + temp_text2, temp_xc1+temp_xc2                
            temp_xc, temp_text = list(zip(*sorted(zip(temp_xc, temp_text))))
            temp, _ = self.getting_index(temp_text, temp_xc, temp, flag)
        return temp       
    def high_cen_func(self, text, top, h, zoom_fac):
        # Get words of head_row and check if the words belongs to head_row
        high_cen = None
        # time_check, time_y = True, 0
        high_y_purp = []
        for cnt, te in enumerate(text):
            te = te.lower()
            if ('srn' in te) or ('cin' in te) or ('company' in te):
                high_y_purp.append(int((top[cnt]+h[cnt]/2)/zoom_fac))

        # Find y_center coordinate of head_row
        if len(high_y_purp) > 1:
            val, cnt = self.subset(high_y_purp, 15, 'medi')
            if max(cnt) > 1:
                high_cen = val[cnt.index(max(cnt))]

        return high_cen


    def get_headpage(self, img, conf, dig, temp_page_digit):
        '''
        Head_page has the words such as “bench”, “Date and Time”, “Court”, head_row 
        Head_row: Row including words of ”SR NO”, “CP NO”, “Property”, ...
        1. Extract all text of page
        2. Get words of head_row and check if the words belongs to head_row
        3. Find y_center coordinate of head_row
        4. When head_page(or y_center coordinae of head_row) exists, get heading.
        5. When head_page(or y_center coordinae of head_row) exists, get index and self.cols.
        '''
        global medi_val 
        zoom_fac = 1
        # Extract all text of page
        if not dig: ## for scan
            temp_page_digit = False
            zoom_fac = 1    
            # img = cv2.resize(img, None, fx=zoom_fac, fy=zoom_fac)
            text, left, top, w, h, accu, xc, yc = self.getting_textdata(img, conf, zoom_fac, 0)
            
        else: ## for digit
            top, left, h, w, text = self.digit_value
            top, left, h, w, text = zip(*sorted(zip(top, left, h, w, text)))
            yc, xc = (np.array(top)+np.array(h)/2).tolist(), (np.array(left)+np.array(w)/2).tolist()  
        # yc, xc, top, left, h, w, text = zip(*sorted(zip(yc, xc, top, left, h, w, text)))
        if len(text) == 0:
            raise Exception("08")
        ##### Getting mean width and height #####
        medi_w, medi_h = int(np.median(w)), int(np.median(h)*1.1) 
        medi_val = [int(medi_w/zoom_fac)*0.7, int(medi_h/zoom_fac)]
        high_cen = self.high_cen_func(text, top, h, zoom_fac)
        if high_cen is not None:
            global index
            # img_text_1 = self.img[high_cen-28:high_cen+32]
            img_text_2 = img[high_cen-28:high_cen+32]
            zoom_fac = 1
            index = self.Index(img_text_2, zoom_fac)
            # index[0] = max(min([v for v in index if v > 0]) - 100, 10)
            if index.count(-1) > 1:
                zoom_fac = 2
                index = self.Index(img_text_2, zoom_fac)
            if index.count(-1) > 2:  raise Exception("03")            

        return high_cen, temp_page_digit#, temp, temp_page_digit

    def subset(self, set, lim, loc):
        '''
        set: one or multi list or array, lim: size, loc:location(small, medi, large)
        This function reconstructs set according to size of lim in location of loc.
        '''
        cnt, len_set = 0, len(set)        
        v_coor_y1, index_ = [], []
        pop = []
        for i in range(len_set):
            if i < len_set-1:
                try:
                    condition = set[i+1][0] - set[i][0]
                except:
                    condition = set[i+1] - set[i]
                if condition < lim:
                    cnt = cnt + 1
                    pop.append(set[i])
                else:
                    cnt = cnt + 1
                    pop.append(set[i])
                    pop = np.asarray(pop)
                    try:
                        if loc == "small": v_coor_y1.append([min(pop[:, 0]), min(pop[:, 1]), max(pop[:, 2])])
                        elif loc == "medi": v_coor_y1.append([int(np.median(pop[:, 0])), min(pop[:, 1]), max(pop[:, 2])])
                        else: v_coor_y1.append([max(pop[:, 0]), min(pop[:, 1]), max(pop[:, 2])])
                    except:
                        if loc == "small": v_coor_y1.append(min(pop))
                        elif loc == "medi": v_coor_y1.append(int(np.median(pop)))
                        else: v_coor_y1.append(max(pop))  
                    index_.append(cnt)
                    cnt = 0
                    pop = []
            else:
                cnt += 1
                pop.append(set[i])
                pop = np.asarray(pop)
                try:
                    if loc == "small": v_coor_y1.append([min(pop[:, 0]), min(pop[:, 1]), max(pop[:, 2])])
                    elif loc == "medi": v_coor_y1.append([int(np.median(pop[:, 0])), min(pop[:, 1]), max(pop[:, 2])])
                    else: v_coor_y1.append([max(pop[:, 0]), min(pop[:, 1]), max(pop[:, 2])])
                except:
                    if loc == "small": v_coor_y1.append(min(pop))
                    elif loc == "medi": v_coor_y1.append(int(np.median(pop)))
                    else: v_coor_y1.append(max(pop))                    
                index_.append(cnt)

        return v_coor_y1, index_

    def modify_digit(self, ly, lx):
        '''
        this function is used to get ROI in first page of digital pdf 
        '''
        top, left, h, w, text = self.digit_value
        top, left, h, w = (top - ly).tolist(), (left - lx).tolist(), h.tolist(), w.tolist()
        self.digit_value = list(zip(*sorted(zip(top, left, h, w, text))))
        return self.digit_value[4]
    def min_max_y(self, verlines_y):
        ver_coor_y1, index1 = self.subset(np.sort(verlines_y[:, 0]), 20, 'medi')
        ver_coor_y2, index2 = self.subset(np.sort(verlines_y[:, 1]), 20, 'medi')
        if len(ver_coor_y1) < 3 and sum(index1) < 3:
            raise Exception("06")
        # Find upper limit and under limit of image 
        min_y = ver_coor_y1[index1.index(max(index1))]-2
        max_y = ver_coor_y2[index2.index(max(index2))]+2
        ver_coor_y1 = [ver_coor_y1[i] for i,v in enumerate(index1) if v > 3]
        ver_coor_y2 = [ver_coor_y2[i] for i,v in enumerate(index2) if v > 3]
        if len(ver_coor_y1) > 0:
            min_y = min(ver_coor_y1)
        if len(ver_coor_y2) > 0:
            max_y = max(ver_coor_y2)
        return min_y, max_y
    def getting_range(self):
        '''
        1. Get all vertial lines satisfied some condition
        2. Get all start points and end points of lines by coordinates and counts.
        3. Find upper limit and under limit of image 
        4. Modify horizontal lines
        '''
        self.img = self.img[self.min_y:self.max_y]
        self.img_removedByline = self.img_removedByline[self.min_y:self.max_y]
        self.img = self.border_set(self.img, [0, self.img.shape[1], None, None], 30, [255, 255,255])
        self.img = self.border_set(self.img, [None, None, 0, self.img.shape[0]], 2, [0,0,0])
        self.img_removedByline = self.border_set(self.img_removedByline, [0, self.img.shape[1], None, None], 30, 255)
        rows = self.line_detector(self.img, 'hor')
        cols = self.line_detector(self.img, 'ver')
        rows.sort()
        cols.sort()
        new_cols = []

        for i in range(len(rows)):
            try:
                self.rows.append([rows[i]+self.tk, rows[i+1]-self.tk])
            except:
                pass
        for i in range(len(cols)):
            try:
                new_cols.append([cols[i]+self.tk, cols[i+1]-self.tk])
            except:
                pass   
        ## considering necessary column according to index ##    
        for col in new_cols:
            condi_1 = False
            for ind in index:
                if col[0] < ind < col[1]: 
                    condi_1 = True
                    break
            # condi_2 = col[0] < min([v for v in index if v > 0])
            if condi_1:# or condi_2:
                self.cols.append(col)
        if index[0] == -1:
            self.cols.insert(0, new_cols[0])
        if page_digit: self.get_digit_cen()

        return rows, cols
    def noiseRemoveFromImg(self, th, er):
        #### Remove noise ####
        result = cv2.cvtColor(self.img_removedByline, cv2.COLOR_BGR2GRAY)
        _, self.img_removedByline = cv2.threshold(result, self.ths, 255, cv2.THRESH_BINARY)

        # result = cv2.erode(result, np.ones((er, 2)), iterations=1)
        _, result = cv2.threshold(result, 128, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
        
        nlabels, labels, stats, centroids = cv2.connectedComponentsWithStats(result, None, None, None, 8, cv2.CV_32S)
        sizes = stats[1:, -1] #get CC_STAT_AREA component
        # img2 = np.zeros((labels.shape), np.uint8)

        for i in range(0, nlabels - 1):
            if sizes[i] < th:   #filter small dotted regions
                self.img[labels == i + 1] = [255, 255, 255]
        # self.img_removedByline = cv2.bitwise_not(img2)
        return None      
    def getting_table(self):
        '''
        1. Remove unnecessary columns
        2. Get all horizontal lines
        3. Get upper limit and under limit of image,  and self.rows
        4. Make self.table image using self.cols and self.rows
        '''
        if not page_digit:
            self.noiseRemoveFromImg(10, 2)
        # Get upper limit and under limit of image,  and self.rows
        
        rows, cols = self.getting_range() ## self.rows is defined here.
        ## getting binary table combining horizontal lines and vetical lines ##
        temp = cv2.cvtColor(self.img, cv2.COLOR_BGR2GRAY)
        vertical_lines = np.zeros_like(temp)+255
        horizontal_lines = np.zeros_like(temp)+255
        # Make self.table image using self.cols and self.rows
        self.rows = [v for v in self.rows if v[1]-v[0] > self.lim[1]]
        for col in self.cols:
            vertical_lines[:, col[0]:col[1]] = 0
        for row in self.rows:
            horizontal_lines[row[0]:row[1]] = 0
        img_vh = cv2.addWeighted(vertical_lines, 0.5, horizontal_lines, 0.5, 0.0)
        _, img_vh = cv2.threshold(img_vh, 50, 255, cv2.THRESH_BINARY)
        
        self.table = img_vh
        return None

    def border_set(self, img_, coor, tk, color):
        '''
        coor: [x0, x1, y0, y1] - this denotes border locations.
        tk: border thickness, color: border color.
        '''
        img = img_.copy()
        if coor[0] != None:
            img[:, coor[0]:coor[0]+tk] = color # left vertical
        if coor[1] != None:
            img[:, coor[1]-tk:coor[1]] = color # right vertical
        if coor[2] != None:                    
            img[coor[2]:coor[2]+tk,:] = color # up horizontal
        if coor[3] != None:
            img[coor[3]-tk:coor[3],:] = color # down horizontal          

        return img  

        
    def text_inrange(self, ori_text, yxwh):
        y, x, h, w = yxwh[0], yxwh[1], yxwh[2], yxwh[3]
        text_list = [item for item in ori_text if item[0] > y-3 and item[0] < y+h]
        text = [item[2] for item in text_list if item[1] > x-3 and item[1] < x+w]
        text = ' '.join(text)
        text = re.sub('(___)', '', text)
        return text
        
    def approximate(self, li, limit):
        pre_l = li[0]
        new_li = []
        for l in li:
            if abs(l - pre_l) < limit:
                l = pre_l
            else:
                pre_l = l
            new_li.append(l)
        return new_li

    def get_digit(self, d):
        '''
        This function gets all digital texts and their coordinates.
        '''
        text, left, top, w, h, accu= [], [], [], [], [], []
        page_rot = self.digit_page.rotation
        d = np.array(d)
        text = d[:, 4].tolist()
        coor = d[:, 0:4]
        
        pdf_zoom = 3
        coor = np.apply_along_axis(np.genfromtxt, 1 ,coor)*pdf_zoom
        H, W, _ = self.img.shape

        if page_rot == 0:
            left, top, w, h = coor[:, 0], coor[:, 1], (coor[:,2]-coor[:,0]), (coor[:,3]-coor[:,1])
        elif page_rot == 90:
            left, top, w, h = (W-coor[:, 3]), coor[:, 0], (coor[:,3]-coor[:,1]), (coor[:,2]-coor[:,0])
        elif page_rot == 180:
            left, top, w, h = coor[:, 2], coor[:, 3], (coor[:,0]-coor[:,2]), (coor[:,1]-coor[:,3])
        elif page_rot == 270:left, top, w, h = coor[:,1], (H-coor[:, 2]), (coor[:,3]-coor[:,1]), (coor[:,2]-coor[:,0])
        left, top, w, h = left.astype(int), top.astype(int), w.astype(int), h.astype(int)
        left, top, w, h = left*digit_zoom, top*digit_zoom, w*digit_zoom, h*digit_zoom
        self.digit_value = [top, left, h, w, text]

        return True

    def get_digit_cen(self):
        '''
        This function is used digital pdf.
        Here gets location of y and x, text in every boxes.
        '''
        top, left, h, w, text = self.digit_value
        y_c, x_c = (np.array(top)+np.array(h)/2).tolist(), (np.array(left)+np.array(w)/2).tolist()
        x_c, y_c, text_c = zip(*sorted(zip(x_c, y_c, text)))
        x_c = self.approximate(x_c, int(medi_val[0]*0.6))
        y_c, x_c, text_c = zip(*sorted(zip(y_c, x_c, text_c)))
        y_c = self.approximate(y_c, int(medi_val[1]*0.6))
        y_c, x_c, text_c = zip(*sorted(zip(y_c, x_c, text_c)))
        self.digit_cen_value = list(zip(y_c, x_c, text_c))  
        text_list = [item for item in self.digit_cen_value if item[0] > 0]
        self.digit_cen_value = [item for item in text_list if item[1] > 0]

    def noise_removal(self, img, noise_size):
        '''
        noise_size = [w_noise, h_noise]
        This function removes noises of with noise_size.
        '''
        contours, _ = cv2.findContours(img, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

        for c in contours:
            x, y, w, h = cv2.boundingRect(c)
            
            if h < noise_size[1] and w < noise_size[0]:
                img[y:y+h, x:x+w] = 0
        return img

    def text_region(self, read_img, temp_img):
        '''
        read_img: main_image, temp_img: binary image
        This function removes points and lines noises, then gets exact text range.
        1. Set 4 node(node_size=6) of temp_img into 255
        2. Get only text regions in temp_img. (condition: h < 40 and w > self.tk and h > 8), save the image as temp
        3. Noise remove
        4. Get range including all texts from read_img

        '''
        img_h, img_w = temp_img.shape
        temp_img = self.border_set(temp_img, [0, img_w, 0, img_h], 1, 255) 
        cnt, _ = cv2.findContours(temp_img, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        temp = np.zeros_like(temp_img)+255
        for c in cnt:
            x, y, w, h = cv2.boundingRect(c)
            if h < 35 and w > self.tk and h > 8:# and w < 60:# and h >15:
                # cv2.rectangle(xx, (x, y), (x + w, y + h), (0, 255, 0),1)   
                temp[y:y+h-1, x:x+w-1] = 0
        
        def xyRegion(temp):
            # Get range including all texts from read_img          
            kernel_hor = cv2.getStructuringElement(cv2.MORPH_RECT, (img_w, 1)) # vertical
            kernel_ver = cv2.getStructuringElement(cv2.MORPH_RECT, (1, img_h)) # vertical
            hor_temp = cv2.erode(temp, kernel_hor, iterations=2)     
            ver_temp = cv2.erode(temp, kernel_ver, iterations=2)
            img_vh = cv2.addWeighted(ver_temp, 0.5, hor_temp, 0.5, 0.0)
            _, img_vh = cv2.threshold(img_vh, 50, 255, cv2.THRESH_BINARY)
            img_vh = self.border_set(img_vh, [0, img_w, 0, img_h], 2, 255)
            contours, _ = cv2.findContours(img_vh, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
            x1, x2, y1, y2  = img_w, 0, img_h, 0
            for c in contours:
                x, y, w, h = cv2.boundingRect(c) 
                if w < img_w and h < img_h:
                    if x < x1: x1 = x
                    if y < y1: y1 = y
                    if x+w > x2: x2 = x+w
                    if y+h > y2: y2 = y+h
            return x1,x2,y1,y2    
        x01,x02,y01,y02 = xyRegion(temp)            
        erod_size = 10
        temp = cv2.erode(temp, np.ones((2,erod_size)), iterations=1) # 10 means letter space.
        temp = self.border_set(temp, [0, img_w, 0, img_h], 1, 255) 
        
        # noise remove     
        w_30 = False
        cnt, _ = cv2.findContours(temp, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        ch_w = 15
        for c in cnt:
            x, y, w, h = cv2.boundingRect(c)
            if w > ch_w:
                w_30 = True 
                break
        if w_30:
            for c in cnt:
                x, y, w, h = cv2.boundingRect(c)
                if w < ch_w or h < 15: temp[y:y+h, x:x+w] = 255            

        x1,x2,y1,y2 = xyRegion(temp)

        if x1 > 2: x1 = x1 + int(erod_size/2)
        if x2 < img_w -2: x2 = x2 - int(erod_size/2)
        x1, x2 = max(x1, x01), min(x2, x02)
        y1, y2 = max(y1, y01), min(y2, y02)

        img = read_img[y1:y2, x1:x2]

        pad = 10
        img = np.pad(img, ((pad, pad), (pad, pad), (0,0)),mode='constant', constant_values=255) 

        return img

    def box_text_detection(self):
        '''
        Here gets boxes and texts
        Boxes and texts are corresponding each other
        '''
        img_height, img_width = self.table.shape
        image = self.img.copy()
        box, text = [], []
        contours, _ = cv2.findContours(self.table, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        custom_config = '--psm 6'        
        # temp = cv2.cvtColor(self.img_removedByline, cv2.COLOR_RGB2GRAY)                
        # _, temp_img = cv2.threshold(temp, 230, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
        cnt = 0

        for c in contours:
            x, y, w, h = cv2.boundingRect(c)
            if  w < img_width*0.99 and h < img_height*0.95 and w > self.lim[0] and h > self.lim[1]:
                image = cv2.rectangle(image, (x, y), (x + w, y + h), (0, 0, 255), 2)
                box.append([y, x, h, w])
                if page_digit:
                    # In case of digital pdf
                    text.append(self.text_inrange(self.digit_cen_value, [y, x, h, w]))
                else: 
                    # In case of scanned pdf
                    if (self.img_removedByline[y+5:y+int(h*0.8), x+int(w*0.05):x+int(w*0.8)] == 0).sum() > 10:
                        temp_read = self.img_removedByline[y:y+h+3, x:x+w]
                        img_to_read = self.img[y:y+h+3, x:x+w]
                        # if cnt == 0:
                        #     print("okay")
                        img_to_read = self.text_region(img_to_read,  temp_read)
                        # cv2.imwrite(f"results/img_to_read_{cnt}.png", img_to_read)  
                        if len(np.unique(img_to_read)) > 1:
                            te = pytesseract.image_to_string(img_to_read, config=custom_config)
                            if(len(te) == 0):
                                te = pytesseract.image_to_string(img_to_read, config='--psm 10')
                            ## Modification of text ##   
                            strp_chars = "|^#;$`'-_=*\/‘:¢ \n"
                            te = re.sub('\n+', '\n', te)
                            te = te.replace(':', '')
                            te = te.replace('*', '')
                            # te = re.sub('(:|*|#)', '', te)
                            te = te.replace('\n|\n ', ' ')
                            checkwords, repwords =('{', '}', '!'), ('(', ')', 'I')
                            for check, rep in zip(checkwords, repwords):
                                te = te.replace(check, rep)
                            te = te.strip(strp_chars)
                            while 1:
                                if (te[0:2] in ["l ", "i ", "l\n", "i\n", "| ", "|\n"]):
                                    te = te[2:]
                                elif (te[-2:] in [" l", " i", "\nl", "\ni", " |", "\n|"]):
                                    te = te[0:-2]
                                else: break
                        else: te = ''
                        cnt = cnt + 1
                    else:
                        te = ''
                    text.append(te)

        cv2.imwrite(os.path.join(self.output_dir,'_'.join(("detected",self.img_name+'.jpg'))), image)
        box, text = zip(*sorted(zip(box, text)))
        return list(box), list(text)

    def reconstruction(self, box, text):
        '''
        This function restructs box and text according to difference of rows or column.
        When smaller self.lim, program process current row(or column) into past.
        '''
        box, text = zip(*sorted(zip(box, text)))
        pre_bo = box[0][0]
        new_box = []
        ii = 0
        for bo in box:
            ii = ii+1
            if abs(bo[0] - pre_bo) < self.lim[1]:
                bo[0] = pre_bo
            else:
                pre_bo = bo[0]
            # new_box.append(bo)
        box = list(zip(*box))
        box[0], box[1] = box[1], box[0]
        box = list(zip(*box))

        box, text = zip(*sorted(zip(box, text)))
        pre_bo = box[0][0]
        new_box = []
        for bo in box:
            bo = list(bo)
            if abs(bo[0] - pre_bo) < self.lim[0]:
                bo[0] = pre_bo
            else:
                pre_bo = bo[0]
            new_box.append(bo)

        box = list(zip(*new_box))
        box[0], box[1] = box[1], box[0]
        box = list(zip(*box))
        box, text = zip(*sorted(zip(box, text)))

        return box, text

    def parse_page(self):
        '''
        main process.
        '''
        box, text = [], []
        digit = self.check_scan_or_digit()
        self.preprocess_image()
        #############################
        if not self.headpage_checking:
            global page_digit
            page_digit = self.text_detection(digit)
        if self.headpage_checking:
            self.getting_table()
            box, text = self.box_text_detection()
            box, text = self.reconstruction(box, text)
        return box, text