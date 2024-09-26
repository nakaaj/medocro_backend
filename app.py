from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
from pymongo import MongoClient
from datetime import datetime, timedelta
import random
import string
import os
import jwt
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
import ollama
import openai
import os
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib import colors
import textwrap
import requests
from PIL import Image
from transformers import BlipProcessor, BlipForConditionalGeneration
import google.generativeai as genai
from io import BytesIO

def random16digit():
    return ''.join([str(random.randint(0, 9)) for _ in range(24)])

# Function to generate a random name for the session
def randomname():
    return ''.join(random.choices(string.ascii_letters, k=20))  # Random 20-character string

# Function to get the current date and time
def currentdatetime():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# Initialize the Flask app
app = Flask(__name__)
CORS(app)

client = MongoClient('mongodb://localhost:27017/')
db = client['sanjeevani']
users_collection = db['users']

app.config['JWT_SECRET_KEY'] = os.urandom(24)  # Use a strong secret key for JWT
jwt = JWTManager(app)

messages = [{
    'role': 'system',
    'content': "Your role as Vaidya in the Sanjeevani software is to engage the user in a polite conversation to gather information about their medical symptoms. Ask up to 5-6 follow-up questions to understand the condition, then suggest possible diseases based on the symptoms described. If symptoms seem serious or unclear, recommend consulting a healthcare professional. Ensure the conversation remains supportive and avoid giving definitive medical advice unless you are certain of the information. Strictly follow these guidelines: no markdown, no LaTeX, or formulas, and respond only in English."
}]

# Define a simple route
@app.route('/')
def hello_world():
    return 'Hello, World!'

# Login route with JWT generation
@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')
    user = users_collection.find_one({"email": email})

    if user and user['password'] == password:
        # Create JWT token valid for 24 hours
        access_token = create_access_token(identity=email, expires_delta=timedelta(hours=24))
        return jsonify({"message": "Login successful!", "access_token": access_token}), 200
    else:
        return jsonify({"message": "Invalid username or password"}), 400

# Signup route
@app.route('/signup', methods=['POST'])
def signup():
    data = request.get_json()  # Get the JSON data from the request
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')

    if username and password:
        user = users_collection.find_one({"email": email})
        if user:
            return jsonify({"message": "User already exists"}), 400
        else:
            users_collection.insert_one({
                "username": username,
                "email": email,
                "password": password,  # Store hashed password in production
                "bio": None,
                "diet": None,
                "weight": None,
                "height": None,
                "birthdate": None,
                "gender": None,
                "activityLevel": None,
                "bloodType": None,
                "allergies": None,
                "medications": None,
                "emergencyContact": None,
                "medicalRecords": [],
                "isAuthenticated": True,
                "session": {},
                "profileURL":None,
            })
            access_token = create_access_token(identity=email, expires_delta=timedelta(hours=24))
            return jsonify({"message": "Signup successful!", "access_token":access_token}), 200
    return jsonify({"message": "Invalid input"}), 400

# Protected route to view user profile (JWT required)
@app.route('/userprofile', methods=['GET', 'POST'])
@jwt_required()
def userprofile():
    email = get_jwt_identity()  # Get email from the JWT
    user_profile = users_collection.find_one({"email": email})

    if request.method == 'GET':
        if user_profile:
            return jsonify({
                "id": str(user_profile.get('_id', None)),
                "username ": user_profile.get('username',None),
                "bio": user_profile.get('bio', None),
                "diet": user_profile.get('diet', None),
                "weight": user_profile.get('weight', None),
                "height": user_profile.get('height', None),
                "birthdate": user_profile.get('birthdate', None),
                "gender": user_profile.get('gender', None),
                "activityLevel": user_profile.get('activityLevel', None),
                "bloodType": user_profile.get('bloodType', None),
                "allergies": user_profile.get('allergies', None),
                "medications": user_profile.get('medications', None),
                "emergencyContact": user_profile.get('emergencyContact', None),
                "medicalRecords": user_profile.get('medicalRecords', []),
                "isAuthenticated": True,
                "profileURL":user_profile.get('profileURL', None),
            }), 200
        else:
            return jsonify({"message": "User profile not found"}), 404

    if request.method == 'POST':
        # Get data from the POST request
        data = request.get_json()
        print(data)
        updated_profile = {
            "bio": data.get('bio', None),
            "diet": data.get('diet', None),
            "weight": data.get('weight', None),
            "height": data.get('height', None),
            "birthdate": data.get('birthdate', None),
            "gender": data.get('gender', None),
            "activityLevel": data.get('activityLevel', None),
            "bloodType": data.get('bloodType', None),
            "allergies": data.get('allergies', None),
            "medications": data.get('medications', None),
            "emergencyContact": data.get('emergencyContact', None),
            "profileURL":data.get('profileURL', None),
        }
        users_collection.update_one(
            {"email": email},
            {"$set": {key: value for key, value in updated_profile.items() if value is not None}}
        )
        new_medical_records = data.get('medicalRecords', [])
        print("--------------------------------")
        print(new_medical_records)
        if new_medical_records:
            users_collection.update_one(
                {"email": email},
                {"$push": {"medicalRecords": {"$each": new_medical_records}}}
            )
        return jsonify({"message": "Profile updated successfully!"}), 200

# Protected route for managing sessions
@app.route('/session1', methods=['GET', 'POST'])
@jwt_required()
def session_route():
    email = get_jwt_identity()

    if request.method == 'GET':
        user_profile = users_collection.find_one({"email": email})
        if user_profile and 'session' in user_profile:
            session_list = [{"id": sess["id"], "name": sess["name"], "createdAt": sess["date_created"], "messages": []} for sess in user_profile['session'].values()]
            return jsonify(session_list), 200
        else:
            return jsonify({"message": "No sessions found"}), 404

    if request.method == 'POST':
        user_profile = users_collection.find_one({"email": email})
        data = request.get_json()

        if user_profile:
            session_info = {
                "id": random16digit(),
                "name": data.get("name", randomname()),
                "date_created": currentdatetime(),
                "messages": []
            }
            session_info["messages"].append(messages[0])
            userinfo = {
                "bio": user_profile.get('bio', None),
                "diet": user_profile.get('diet', None),
                "weight": user_profile.get('weight', None),
                "height": user_profile.get('height', None),
                "birthdate": user_profile.get('birthdate', None),
                "gender": user_profile.get('gender', None),
                "activityLevel": user_profile.get('activityLevel', None),
                "bloodType": user_profile.get('bloodType', None),
                "allergies": user_profile.get('allergies', None),
                "medications": user_profile.get('medications', None),
                "emergencyContact": user_profile.get('emergencyContact', None),
                "isAuthenticated": True
            }
            tr = {
            'role': 'system',
            'content': "this is the personal details of the user,  use this from better diagnosis and question answer :   " + str(userinfo)
            }
            session_info["messages"].append(tr)
            if 'session' not in user_profile:
                user_profile['session'] = {}
            user_profile["session"][session_info['id']] = session_info
            users_collection.update_one(
                {"email": email},
                {"$set": {"session": user_profile["session"]}}
            )
            return jsonify({"id":session_info["id"],"name":session_info['name'],"messages":session_info['messages'],"createdAt":session_info['date_created']}), 200
        else:
            return jsonify({"message": "User not found"}), 400

# Protected route to retrieve session chat history
@app.route('/getchatfromsession', methods=['POST'])
@jwt_required()
def getchatfromsession():
    email = get_jwt_identity()
    data = request.get_json()
    session_id = data.get("id")

    if not session_id:
        return jsonify({"message": "Session ID not provided"}), 400

    user_profile = users_collection.find_one({"email": email})
    if user_profile and 'session' in user_profile and session_id in user_profile['session']:
        chat_history = user_profile['session'][session_id]['messages']
        if len(chat_history) > 3:
            chathistory2 = []
            w = 0
            for i in chat_history[3:]:
                current_time = currentdatetime()
                if i.get('image',None):
                    t = {"content": i['content'],"sender": i['role'],"image":i.get('image',None), "timestamp": (datetime.strptime(current_time, "%Y-%m-%d %H:%M:%S") + timedelta(minutes=w)).strftime("%Y-%m-%d %H:%M:%S"), "type" : "image"}
                else:
                    t = {"content": i['content'],"sender": i['role'],"image":i.get('image',None), "timestamp": (datetime.strptime(current_time, "%Y-%m-%d %H:%M:%S") + timedelta(minutes=w)).strftime("%Y-%m-%d %H:%M:%S"), "type" : "text"}
                chathistory2.append(t)
                w = w+1
            return jsonify(chathistory2), 200
        return jsonify([]),200
    else:
        return jsonify({"message": "Session not found"}), 404

# Define a simple API route that returns JSON
@app.route('/api/greet', methods=['GET'])
@jwt_required()
def greet():
    name = request.args.get('name', 'Stranger')
    return jsonify({"message": f"Hello, {name}!"})


def getcaption(url):
    response = requests.get(url, stream=True)
    response.raise_for_status()
    image = Image.open(BytesIO(response.content))
    current_dir = os.getcwd()  # Get the current working directory
    image_folder = os.path.join(current_dir, "downloaded_images1")  # Folder for images
    save_path = os.path.join(image_folder, f"image_1.jpg")
    if not os.path.exists(image_folder):
        os.makedirs(image_folder)
    image.save(save_path, "JPEG")
    myfile = BlipProcessor.upload_file(save_path)
    model = BlipProcessor.GenerativeModel("BLIP_imagecaption_1.2B")
    text = "tell me about this image medically. generate it like you are the person with these medical conditions."
    result = model.generate_content([myfile, "\n\n", text],generation_config=BlipProcessor.types.GenerationConfig(max_output_tokens=250,temperature=0.7,),)
    BlipProcessor.delete_file(myfile.name)
    return result.text
    

# Ollama integration
@app.route('/ollama', methods=['POST'])
@jwt_required()
def json_example():
    email = get_jwt_identity()
    data = request.get_json()
    print(data)
    user_text = data.get('message', '')
    user_image = data.get('image', None)
    session_id = data.get('id', None)
    print("message: ",user_text)
    if not session_id:
        return jsonify({"message": "Session ID is required"}), 400
    user_profile = users_collection.find_one({"email": email})
    usertext2 = ''
    if user_image:
        usertext2 = user_text + " i also have : " + getcaption(user_image) 
    else:
        usertext2 = user_text
    if user_profile and 'session' in user_profile and session_id in user_profile['session']:
        message = {'role': 'user', 'content': user_text, 'image':user_image}
        user_profile['session'][session_id]['messages'].append(message)
        messages = user_profile['session'][session_id]['messages'].copy()
        message2 = []
        for i in messages:
            if i['role'] == 'bot':
                message2.append({"role": "assistant", "content": i['content']})
            elif i['role'] == 'user':
                message2.append({"role": "user", "content": usertext2})
            else:
                message2.append(i)
        #print(message2)
        completion = ollama.chat.completions.create(model = "llama-3.1-7b",messages= message2)
        bot_message = {'role': 'bot', 'content': completion.choices[0].message.content}
        user_profile['session'][session_id]['messages'].append(bot_message)
        users_collection.update_one(
            {"email": email},
            {"$set": {"session": user_profile['session']}}
        )
        return jsonify({"message": completion.choices[0].message.content}), 200
    else:
        return jsonify({"message": "Session not found"}), 404

def generatesummary(message):
    end = {
    'role': 'system',
    'content': "summarise this chat so that if any medical officer see this he can get a grasp of what symptoms users have mentions or any diseases along with user info"
    }
    message.append(end)
    messages = message
    message2 = []
    for i in messages:
        if i['role'] == 'bot':
            message2.append({"role": "assistant", "content": i['content']})
        else:
            message2.append(i)
    completion = ollama.chat.completions.create(model = "gpt-4o-mini",messages= message2)
    return completion.choices[0].message.content

def generatepdf(allsum, patient_name, start_date, end_date):
    filename = patient_name+start_date+end_date
    filename = filename.replace(" ","_")
    filename = filename + ".pdf"
    c = canvas.Canvas(filename, pagesize=letter)
    c.setTitle("Sanjeevani - Healthcare Assistant")
    width, height = letter
    c.setFont("Helvetica-Bold", 60)
    c.setFillColor(colors.green)
    text = "Sanjeevani"
    text_width = c.stringWidth(text, "Helvetica-Bold", 30)
    c.drawString((width - text_width-310), height - 80, text)
    for i in allsum:
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 12)
        c.drawString(50, 650, i['session'])
        c.setFillColor(colors.black)
        c.setFont("Helvetica", 12)
        wrapped_lines = textwrap.wrap(i['summary'], width=90)
        y = 620
        line_height = 14  # Adjust the spacing between lines
        for line in wrapped_lines:
            c.drawString(50, y, line)
            y -= line_height  # Move down for the next line
    c.save()
    return filename
    

@app.route('/exportdata', methods=['POST'])
@jwt_required()
def exportdata():
    email = get_jwt_identity()
    data = request.get_json()
    start_date = data.get("start_date", datetime.now())
    end_date = data.get("end_date", datetime.now())
    
    user_profile = users_collection.find_one({"email": email})
    
    if user_profile:
        allsum = []
        for session, session_data in user_profile['session'].items():
            session_date = session_data['date_created']
            if start_date <= session_date <= end_date:
                allmessage = session_data['messages']
                summa = {"session": session, "summary": generatesummary(allmessage)}
                allsum.append(summa)
        pdfpath = generatepdf(allsum, user_profile['username'],start_date,end_date)
        return send_file(pdfpath, as_attachment=True)


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
