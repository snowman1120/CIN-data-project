# Description:
# This script is an object-oriented approach to table extraction from scaned PDFs or image.

import os
import shutil
import logging
import datetime
from CIN_parser import Document
from CIN_post_proc import post_processing

def clear_contents(dir_path):
    '''
    Deletes the contents of the given filepath. Useful for testing runs.
    '''
    filelist = os.listdir(dir_path)
    if filelist:

        for f in filelist:
            if os.path.isdir(os.path.join(dir_path, f)):
                shutil.rmtree(os.path.join(dir_path, f))
            else:
                os.remove(os.path.join(dir_path, f))
    return None

def parse_document(data_dir, output_dir, doc_path):
    '''
    This is a separate function to facilitate parallelization.
    Returns a dictionary in case of an error, else None.
    '''
    pdf_doc = Document(doc_path, data_dir, output_dir)

    return pdf_doc.parse_doc() 

def makedir(dir):
    try:
        os.mkdir(dir)
    except:
        pass

def main(data_dir, output_dir, err_dir):
    '''
    Main control flow:
        1. Checks if required folders exist; if not, creates them
        2. Loops over each PDF file in data_path and calls parse_doc().
        3. Output xlsx files are written to output_path.
    '''
    # Check if organizing folders exist
    for i in [data_dir, output_dir, err_dir]:
        try:
            if i == data_dir and not os.path.exists(data_dir):
                raise Exception("Data folder is missing or not assigned.")
            else:
                os.mkdir(i)
        except FileExistsError:
            continue
    # Clear output folder
    clear_contents(output_dir)
    clear_contents(err_dir)

    # Get list of pdfs to parse
    pdf_list = [f for f in os.listdir(data_dir) if (f.split('.')[-1].lower() in ['pdf'])]
    pdf_list.sort()
    logger.info(f"{len(pdf_list)} file(s) detected.")
    doc_Box, doc_text, success_pdfs = [], [], []
    start = datetime.datetime.now()
    # Loop over PDF files, create Document objects, call Document.parse()
    cnt = 0
    for i in pdf_list:
        cnt = cnt + 1
        logger.info(f"Parsing file_{cnt}/{len(pdf_list)}: {os.path.join(data_dir, i)}")
        pdf_doc = Document(i, data_dir, output_dir)
        box, text = pdf_doc.parse_doc()
        if text is None:
            shutil.copyfile(os.path.join(data_dir, i), os.path.join(err_dir, i))
        else:
            doc_Box.append(box)
            doc_text.append(text)
            success_pdfs.append(i)
    save_path = os.path.join(output_dir, 'main.xlsx')
    # post processing for all pdfs
    try:
        if len(doc_text) > 0:
            post_processing(doc_Box, doc_text, save_path, success_pdfs)
        try:
            os.remove("results/temp.jpg")
        except:
            pass
    except: pass
    duration = datetime.datetime.now() - start
    logger.info(f"Success: {len(success_pdfs)}, Failed: {len(pdf_list)-len(success_pdfs)}")
    logger.info(f"Time taken: {duration}")

    return None

if __name__ == "__main__":

    # Key paths and parameters
    DATA_DIR = "inputs"
    OUTPUT_DIR = "results"
    ERR_DIR = "failed"

    # Initialize logger
    if os.path.exists('parse_table.log'):
        os.remove('parse_table.log')
    logger = logging.getLogger('parse_table')
    logger.setLevel(logging.INFO)
    ch = logging.StreamHandler()
    fh = logging.FileHandler('parse_table.log')
    logger.addHandler(ch)
    logger.addHandler(fh)

    # Run main control flow    
    main(DATA_DIR, OUTPUT_DIR, ERR_DIR)

    
    
    

