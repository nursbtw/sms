from flask import Flask, render_template, request, jsonify
import os
import json
from datetime import datetime
import pandas as pd
import requests

app = Flask(__name__)

# Store SMS reports (max 100 entries)
sms_reports = []
MAX_REPORTS = 100

# Configure upload folder
UPLOAD_FOLDER = '/tmp'
ALLOWED_EXTENSIONS = {'txt', 'xlsx', 'xls'}

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# API Configuration
SMS_API_CONFIG = {
    'API_URL': os.environ.get('SMS_API_URL', 'https://yurticisms1.com/sms_api'),
    'USERNAME': os.environ.get('SMS_USERNAME', ''),
    'PASSWORD': os.environ.get('SMS_PASSWORD', ''),
    'DATACODING': 'turkish'
}

def validate_phone_number(number):
    """
    Geçerli telefon numarası formatları:
    - 5051234567 (10 haneli)
    - 05051234567 (11 haneli, 0 ile başlayan)
    - 905051234567 (12 haneli, 90 ile başlayan)
    - +905051234567 (13 haneli, +90 ile başlayan)
    """
    if not number:
        return None
        
    # Remove any non-digit characters (including '+')
    number = ''.join(filter(str.isdigit, str(number)))
    
    # Number must be between 10 and 12 digits
    if len(number) < 10 or len(number) > 12:
        return None
        
    # Handle different formats
    if len(number) == 10:  # 5051234567
        if not number.startswith('5'):
            return None
        number = '90' + number
    elif len(number) == 11:  # 05051234567
        if not number.startswith('0'):
            return None
        if not number[1] == '5':
            return None
        number = '9' + number[1:]  # Remove 0 and add 9
    elif len(number) == 12:  # 905051234567
        if not number.startswith('90'):
            return None
        if not number[2] == '5':
            return None
    
    # Final validation
    if not number.startswith('90') or not number[2] == '5':
        return None
        
    return number

def format_phone_number(number):
    """
    Telefon numarasını formatlar ve doğrular.
    Geçerli formatlar:
    - 5051234567
    - 05051234567
    - 905051234567
    - +905051234567
    """
    validated = validate_phone_number(number)
    if validated:
        return validated
    return None

def read_numbers_from_file(file):
    filename = file.filename.lower()
    valid_numbers = []
    invalid_numbers = []
    
    if filename.endswith('.txt'):
        content = file.read().decode('utf-8')
        numbers = content.strip().split('\n')
        
    elif filename.endswith(('.xlsx', '.xls')):
        df = pd.read_excel(file)
        numbers = df.iloc[:, 0].tolist()  # Read first column
        
    else:
        return [], []
        
    for number in numbers:
        formatted = format_phone_number(str(number).strip())
        if formatted:
            valid_numbers.append(formatted)
        else:
            invalid_numbers.append(str(number).strip())
            
    return valid_numbers, invalid_numbers

def send_sms_batch(numbers, message):
    # Format phone numbers
    formatted_numbers = [num for num in [format_phone_number(num) for num in numbers] if num is not None]
    
    if not formatted_numbers:
        return {"Status": "Error", "Message": "Geçerli telefon numarası bulunamadı"}
    
    payload = {
        "Username": SMS_API_CONFIG['USERNAME'],
        "Password": SMS_API_CONFIG['PASSWORD'],
        "DataCoding": SMS_API_CONFIG['DATACODING'],
        "Text": message,
        "To": formatted_numbers
    }
    
    try:
        # Basic headers
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        
        response = requests.post(
            SMS_API_CONFIG['API_URL'],
            json=payload,
            headers=headers,
            timeout=30
        )
        
        try:
            response_json = response.json()
            return response_json
        except json.JSONDecodeError:
            return {"Status": "Error", "Message": "API geçersiz yanıt döndürdü"}
        
    except requests.exceptions.RequestException as e:
        return {"Status": "Error", "Message": f"API Bağlantı Hatası: {str(e)}"}

def get_sms_report(message_id):
    payload = {
        "Username": SMS_API_CONFIG['USERNAME'],
        "Password": SMS_API_CONFIG['PASSWORD'],
        "MessageId": message_id
    }
    
    try:
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        
        response = requests.post(
            SMS_API_CONFIG['API_URL'],
            json=payload,
            headers=headers,
            timeout=30
        )
        
        try:
            response_json = response.json()
            return response_json
        except json.JSONDecodeError:
            return {"Status": "Error", "Message": "API yanıtı işlenemedi"}
            
    except requests.exceptions.RequestException as e:
        return {"Status": "Error", "Message": str(e)}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/send_sms', methods=['POST'])
def send_sms():
    message = request.form.get('message', '').strip()
    if not message:
        return jsonify({"status": "error", "message": "Mesaj boş olamaz"})
        
    # Get numbers from both manual input and file
    numbers = set()
    invalid_numbers = set()
    
    # Process manual numbers
    manual_numbers = request.form.get('manual_numbers', '').strip()
    if manual_numbers:
        for number in manual_numbers.split('\n'):
            number = number.strip()
            if number:
                formatted = format_phone_number(number)
                if formatted:
                    numbers.add(formatted)
                else:
                    invalid_numbers.add(number)
    
    # Process file if uploaded
    if 'number_file' in request.files:
        file = request.files['number_file']
        if file and file.filename:
            valid_file_numbers, invalid_file_numbers = read_numbers_from_file(file)
            numbers.update(valid_file_numbers)
            invalid_numbers.update(invalid_file_numbers)
    
    if not numbers:
        return jsonify({
            "status": "error",
            "message": "Geçerli telefon numarası bulunamadı",
            "invalid_numbers": list(invalid_numbers)
        })
    
    # Send SMS
    numbers_list = list(numbers)
    response = send_sms_batch(numbers_list, message)
    
    if response.get('Status') == 'Error':
        return jsonify({
            "status": "error",
            "message": response.get('Message', 'Bilinmeyen bir hata oluştu'),
            "invalid_numbers": list(invalid_numbers)
        })
    
    # Create report entry
    report_entry = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "message": message,
        "numbers": numbers_list,
        "message_id": response.get('MessageId'),
        "report": response.get('Report', {}).get('List', [])
    }
    
    # Add to reports list
    sms_reports.append(report_entry)
    if len(sms_reports) > MAX_REPORTS:
        sms_reports.pop(0)  # Remove oldest report
    
    return jsonify({
        "status": "success",
        "message": "SMS gönderimi başarılı",
        "message_id": response.get('MessageId'),
        "invalid_numbers": list(invalid_numbers),
        "all_reports": sms_reports
    })

@app.route('/check_status/<message_id>')
def check_status(message_id):
    response = get_sms_report(message_id)
    return jsonify(response)

if __name__ == '__main__':
    app.run(debug=True)
