import streamlit as st
import pytesseract
from PIL import Image
import pdf2image  # Alternative to PyMuPDF
import pdfplumber 
import re
import pandas as pd
import os
import io
from datetime import datetime
from supabase import create_client, Client

# Set Tesseract path
pytesseract.pytesseract.tesseract_cmd = r"/usr/bin/tesseract"

# Set Streamlit page configuration
st.set_page_config(page_title="Receipt Scanner", page_icon="🥾", layout="centered")

# Ensure uploads directory exists
if not os.path.exists("uploads"):
    os.makedirs("uploads")

# Supabase configuration
SUPABASE_URL = "your url"
SUPABASE_KEY = "your key"
# Initialize Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Function to extract vendor name
def extract_vendor_name(text):
    lines = text.split("\n")
    for line in lines:
        trimmed = line.strip()
        if trimmed and len(trimmed) > 1 and not re.search(r"total|amount|invoice|order", trimmed, re.IGNORECASE):
            return trimmed
    return "Unknown Vendor"

# Function to extract transaction ID
def extract_transaction_id(text):
    patterns = [
        r'Transaction\s*ID[:#]*\s*([A-Za-z0-9-]+)',
        r'Order #[:\s]*([A-Za-z0-9-]+)',
        r'Invoice #[:\s]*([A-Za-z0-9-]+)'
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    return "N/A"

# Function to extract total amount
def extract_total_amount(text):
    total_amount_patterns = [
        r'Total[:\s]*\$?([\d,.]+)',
        r'Amount\s*Due[:\s]*\$?([\d,.]+)',
        r'Grand Total[:\s]*\$?([\d,.]+)',
        r'Sum[:\s]*\$?([\d,.]+)'
    ]
    for pattern in total_amount_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    return "N/A"

# Function to process an image with OCR
def process_receipt(image):
    text = pytesseract.image_to_string(image)
    return {
        "Vendor_Name": str(extract_vendor_name(text)),
        "Transaction_ID": str(extract_transaction_id(text)),
        "Total_Amount": str(extract_total_amount(text)),
        "Timestamp": str(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    }, text

## Function to process PDF using pdf2image & pdfplumber
def process_pdf(pdf_file):
    """Extract text from PDF using pdfplumber (if possible) and pdf2image"""
    extracted_text = ""

    try:
        # Try using pdfplumber first (faster for text-based PDFs)
        with pdfplumber.open(pdf_file) as pdf:
            for page in pdf.pages:
                extracted_text += page.extract_text() + "\n"

        # If pdfplumber fails, fallback to OCR
        if not extracted_text.strip():
            pdf_images = pdf2image.convert_from_bytes(pdf_file.read())
            for img in pdf_images:
                extracted_text += pytesseract.image_to_string(img) + "\n"

    except Exception as e:
        st.error(f"Error processing PDF: {e}")
        return "Error"

    return extracted_text


# Streamlit App UI
st.title("Receipt Scanner (Images & PDFs)")
st.subheader("Upload an Image or PDF Receipt")

uploaded_file = st.file_uploader("Choose an image or PDF file", type=["jpg", "jpeg", "png", "pdf"])
if uploaded_file is not None:
    file_extension = uploaded_file.name.split(".")[-1].lower()
    extracted_text = ""
    result = {}
    
    if file_extension in ["jpg", "jpeg", "png"]:
        st.subheader("Uploaded Image")
        image = Image.open(uploaded_file)
        st.image(image, width=300)
        with st.spinner("Processing image..."):
            result, extracted_text = process_receipt(image)
    
    elif file_extension == "pdf":
        with st.spinner("Processing PDF..."):
            extracted_text = process_pdf_with_ocr(uploaded_file)
            result = {
                "Vendor_Name": extract_vendor_name(extracted_text),
                "Transaction_ID": extract_transaction_id(extracted_text),
                "Total_Amount": extract_total_amount(extracted_text),
                "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
    
    if result and extracted_text:
        df = pd.DataFrame([result])
        st.subheader("Extracted Information")
        st.table(df)
        
        with st.expander("View Raw OCR Text"):
            st.text_area("Extracted Text", extracted_text, height=200)
        
        # Save to Supabase Database
        data, count = supabase.table("receipts").insert(result).execute()
        st.success("Receipt data saved to Supabase!")
        
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button("Download Data as CSV", csv, "receipt_data.csv", "text/csv")
        
        if st.button("Scan Another Receipt"):
            st.session_state.pop('history', None)
            st.rerun()

if 'history' in st.session_state and st.session_state.history:
    with st.expander("Receipt History"):
        history_df = pd.DataFrame(st.session_state.history)
        st.dataframe(history_df)
        csv_history = history_df.to_csv(index=False).encode('utf-8')
        st.download_button("Download All History as CSV", csv_history, "receipt_history.csv", "text/csv")

