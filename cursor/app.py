from flask import Flask, render_template, request, jsonify
import os
import json
from datetime import datetime
import pandas as pd
import requests
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# Store SMS reports (max 100 entries)
sms_reports = []
MAX_REPORTS = 100

# Configure upload folder
UPLOAD_FOLDER = '/tmp'  # Vercel için /tmp kullanıyoruz
ALLOWED_EXTENSIONS = {'txt', 'xlsx', 'xls'}

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Debug print to check environment variables
print("[DEBUG] Environment variables:")
print(f"SMS_API_URL: {os.environ.get('SMS_API_URL')}")
print(f"SMS_USERNAME: {os.environ.get('SMS_USERNAME')}")
print(f"SMS_PASSWORD: {os.environ.get('SMS_PASSWORD')}")

# API Configuration with default values for local development
SMS_API_CONFIG = {
    'API_URL': os.environ.get('SMS_API_URL', 'https://yurticisms1.com/index.php'),
    'USERNAME': os.environ.get('SMS_USERNAME', 'user'),
    'PASSWORD': os.environ.get('SMS_PASSWORD', 'Tr**ys^4e'),
    'DATACODING': 'turkish'
}

print("[DEBUG] Final API Configuration:")
print(json.dumps(SMS_API_CONFIG, indent=2))

# Validate API configuration
if not SMS_API_CONFIG['API_URL']:
    raise ValueError("SMS_API_URL is not configured. Please check your .env file.")
if not SMS_API_CONFIG['USERNAME']:
    raise ValueError("SMS_USERNAME is not configured. Please check your .env file.")
if not SMS_API_CONFIG['PASSWORD']:
    raise ValueError("SMS_PASSWORD is not configured. Please check your .env file.")

def validate_phone_number(number):
    """
    Geçerli telefon numarası formatları:
    - 5051234567 (10 haneli)
    - 05051234567 (11 haneli, 0 ile başlayan)
    - 905051234567 (12 haneli, 90 ile başlayan)
    - +905051234567 (13 haneli, +90 ile başlayan)
    """
    if not number:
        print(f"Boş numara")
        return None
        
    # Remove any non-digit characters (including '+')
    number = ''.join(filter(str.isdigit, str(number)))
    print(f"Temizlenmiş numara: {number}")
    
    # Number must be between 10 and 12 digits
    if len(number) < 10 or len(number) > 12:
        print(f"Geçersiz uzunluk: {len(number)} hane")
        return None
        
    # Handle different formats
    try:
        if len(number) == 10:  # 5051234567
            number = '90' + number
            
        elif len(number) == 11:  # 05051234567
            if number.startswith('0'):
                number = '90' + number[1:]
            
        # For 12-digit numbers (905051234567), keep as is
            
        print(f"Son format: {number}")
        return number
        
    except Exception as e:
        print(f"Hata oluştu: {str(e)}")
        return None

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
    
    print(f"[DEBUG] Sending SMS to numbers: {formatted_numbers}")
    print(f"[DEBUG] Message content: {message}")
    
    # Format numbers as string with commas
    numbers_str = ",".join(formatted_numbers)
    
    # Prepare parameters
    params = {
        "user": SMS_API_CONFIG['USERNAME'],
        "pwd": SMS_API_CONFIG['PASSWORD'],
        "msg": message,
        "gsm": numbers_str
    }
    
    try:
        print("[DEBUG] Sending API request...")
        print(f"[DEBUG] API URL: {SMS_API_CONFIG['API_URL']}")
        print(f"[DEBUG] Parameters: {json.dumps(params, indent=2)}")
        
        response = requests.get(
            SMS_API_CONFIG['API_URL'],
            params=params,
            timeout=30
        )
        
        print(f"[DEBUG] API Response Status Code: {response.status_code}")
        print(f"[DEBUG] API Response Content: {response.text}")
        
        response_text = response.text.strip()
        
        # Check if response is an error page
        if "<html" in response_text.lower():
            print("[DEBUG] Received HTML response instead of expected API response")
            return {
                "Status": "Error",
                "Message": "API bağlantı hatası: Sunucu yanıt vermiyor"
            }
            
        # Parse the response
        if "ok" in response_text.lower():
            return {
                "Status": "Success",
                "Message": "SMS gönderimi başarılı"
            }
        else:
            error_msg = response_text if response_text else "Bilinmeyen hata"
            return {
                "Status": "Error",
                "Message": f"API Hatası: {error_msg}"
            }
            
    except requests.exceptions.RequestException as e:
        print(f"[DEBUG] API Request Error: {str(e)}")
        return {"Status": "Error", "Message": f"API Bağlantı Hatası: {str(e)}"}

def get_sms_report(message_id):
    params = {
        "user": SMS_API_CONFIG['USERNAME'],
        "pwd": SMS_API_CONFIG['PASSWORD'],
        "type": "2",
        "id": message_id
    }
    
    try:
        response = requests.get(
            SMS_API_CONFIG['API_URL'],
            params=params,
            timeout=30
        )
        
        response_text = response.text.strip()
        
        if "<html" in response_text.lower():
            return {"Status": "Error", "Message": "API bağlantı hatası"}
            
        return {
            "Status": "Success",
            "Message": response_text
        }
            
    except requests.exceptions.RequestException as e:
        return {"Status": "Error", "Message": str(e)}

# Vercel için index handler
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def catch_all(path):
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
    print(f"Gelen manuel numaralar: {manual_numbers}")  # Debug log
    
    if manual_numbers:
        for number in manual_numbers.split('\n'):
            number = number.strip()
            if number:
                print(f"İşlenen numara: {number}")  # Debug log
                formatted = format_phone_number(number)
                if formatted:
                    print(f"Formatlanmış numara: {formatted}")  # Debug log
                    numbers.add(formatted)
                else:
                    print(f"Geçersiz numara: {number}")  # Debug log
                    invalid_numbers.add(number)
    
    # Process file if uploaded
    if 'number_file' in request.files:
        file = request.files['number_file']
        if file and file.filename:
            print(f"Dosyadan numara okunuyor: {file.filename}")  # Debug log
            valid_file_numbers, invalid_file_numbers = read_numbers_from_file(file)
            numbers.update(valid_file_numbers)
            invalid_numbers.update(invalid_file_numbers)
    
    print(f"Geçerli numaralar: {numbers}")  # Debug log
    print(f"Geçersiz numaralar: {invalid_numbers}")  # Debug log
    
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

# Development server
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 3000)))
