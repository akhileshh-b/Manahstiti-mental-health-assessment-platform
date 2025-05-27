from flask import Flask, request, jsonify, render_template, session
from flask_cors import CORS
import sqlite3
import pandas as pd
import numpy as np
import pickle
import xgboost as xgb
import requests
import os
from datetime import datetime
import json
import secrets
from dotenv import load_dotenv
import uuid

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', os.environ.get('SECRET_KEY', secrets.token_hex(32)))
CORS(app)

# Configuration
GROQ_API_KEY = os.environ.get('GROQ_API_KEY')
GROQ_API_URL = os.environ.get('GROQ_API_URL', 'https://api.groq.com/openai/v1/chat/completions')
GROQ_MODEL = os.environ.get('GROQ_MODEL', 'llama-3.3-70b-versatile')

# Database Configuration
DATABASE_NAME = os.environ.get('DATABASE_NAME', 'manahstiti.db')

# ML Model Configuration
MODEL_PATH = os.environ.get('MODEL_PATH', 'reference/mental_health_xgboost_model.pkl')
LABEL_ENCODER_PATH = os.environ.get('LABEL_ENCODER_PATH', 'reference/mental_health_label_encoder.pkl')

# Server Configuration
HOST = os.environ.get('HOST', '0.0.0.0')
PORT = int(os.environ.get('PORT', 5000))

# Chat memory file
CHAT_MEMORY_FILE = 'chat_memories.json'

# Load ML models using joblib (better for sklearn/xgboost models)
try:
    import joblib
    model = joblib.load(MODEL_PATH)
    label_encoder = joblib.load(LABEL_ENCODER_PATH)
    print("✅ ML models loaded successfully")
except Exception as e:
    print(f"❌ Error loading ML models: {e}")
    try:
        # Fallback to pickle if joblib fails
        with open(MODEL_PATH, 'rb') as f:
            model = pickle.load(f)
        with open(LABEL_ENCODER_PATH, 'rb') as f:
            label_encoder = pickle.load(f)
        print("✅ ML models loaded successfully (using pickle fallback)")
    except Exception as e2:
        print(f"❌ Error loading ML models with fallback: {e2}")
        model = None
        label_encoder = None

# Simple JSON-based memory functions
def get_user_id():
    """Generate a consistent user ID for memory storage"""
    if 'user_id' not in session:
        session['user_id'] = str(uuid.uuid4())
    return session['user_id']

def load_chat_memories():
    """Load chat memories from JSON file"""
    try:
        if os.path.exists(CHAT_MEMORY_FILE):
            with open(CHAT_MEMORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    except Exception as e:
        print(f"❌ Error loading chat memories: {e}")
        return {}

def save_chat_memories(memories):
    """Save chat memories to JSON file"""
    try:
        with open(CHAT_MEMORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(memories, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"❌ Error saving chat memories: {e}")
        return False

def store_conversation(user_id, user_message, ai_response):
    """Store conversation in JSON memory"""
    try:
        memories = load_chat_memories()
        
        if user_id not in memories:
            memories[user_id] = []
        
        # Add new conversation
        conversation = {
            'timestamp': datetime.now().isoformat(),
            'user': user_message,
            'ai': ai_response
        }
        
        memories[user_id].append(conversation)
        
        # Keep only last 20 conversations per user to prevent file from getting too large
        if len(memories[user_id]) > 20:
            memories[user_id] = memories[user_id][-20:]
        
        save_chat_memories(memories)
        print(f"✅ Stored conversation for user: {user_id}")
        return True
        
    except Exception as e:
        print(f"❌ Error storing conversation: {e}")
        return False

def get_chat_history(user_id):
    """Get chat history for a user"""
    try:
        memories = load_chat_memories()
        return memories.get(user_id, [])
    except Exception as e:
        print(f"❌ Error getting chat history: {e}")
        return []

def create_conversation_context(chat_history):
    """Create conversation context from chat history"""
    if not chat_history:
        return ""
    
    context = "\n\nPrevious conversation history:\n"
    for conversation in chat_history:
        context += f"User: {conversation['user']}\n"
        context += f"AI: {conversation['ai']}\n"
    
    context += "\nUse this conversation history to provide consistent and personalized responses. Remember details about the user.\n"
    return context

def clear_json_after_chat():
    """Clear the JSON file after each chat to prevent long conversations"""
    try:
        if os.path.exists(CHAT_MEMORY_FILE):
            os.remove(CHAT_MEMORY_FILE)
            print("✅ JSON memory file cleared after chat")
        return True
    except Exception as e:
        print(f"❌ Error clearing JSON memory: {e}")
        return False

# Initialize database
def init_db():
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    
    # Create questions table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY,
            dimension TEXT,
            question TEXT,
            high_impact BOOLEAN DEFAULT FALSE
        )
    ''')
    
    # Create resources table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS resources (
            id INTEGER PRIMARY KEY,
            category TEXT,
            resource_type TEXT,
            content TEXT
        )
    ''')
    
    conn.commit()
    conn.close()

# Initialize questions from 50questions.txt
def populate_questions():
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    
    # Check if questions already exist
    cursor.execute('SELECT COUNT(*) FROM questions')
    if cursor.fetchone()[0] > 0:
        conn.close()
        return
    
    questions_data = [
        # Mood & Emotions (1-10)
        (1, "Mood & Emotions", "How often do you feel happy during the day?", False),
        (2, "Mood & Emotions", "How stable has your mood been recently?", False),
        (3, "Mood & Emotions", "How often do you feel overwhelmed by emotions?", False),
        (4, "Mood & Emotions", "How easily do you get irritated or frustrated?", False),
        (5, "Mood & Emotions", "How frequently do you feel hopeless?", True),  # High impact
        (6, "Mood & Emotions", "How often do you laugh or feel joy in a day?", False),
        (7, "Mood & Emotions", "How do you feel about yourself generally?", False),
        (8, "Mood & Emotions", "How often do you feel emotionally numb?", False),
        (9, "Mood & Emotions", "How often do you cry or feel like crying?", True),  # High impact
        (10, "Mood & Emotions", "How well can you manage your emotional responses?", False),
        
        # Stress & Anxiety (11-20)
        (11, "Stress & Anxiety", "How stressed do you feel about studies or exams?", False),
        (12, "Stress & Anxiety", "How often do you feel anxious without a clear reason?", False),
        (13, "Stress & Anxiety", "How well can you calm yourself when anxious?", False),
        (14, "Stress & Anxiety", "How often do you experience panic or racing thoughts?", False),
        (15, "Stress & Anxiety", "How worried are you about the future?", False),
        (16, "Stress & Anxiety", "How often do you feel under too much pressure?", False),
        (17, "Stress & Anxiety", "How do you feel before submitting assignments or tests?", False),
        (18, "Stress & Anxiety", "How often does your mind feel 'too full' or cluttered?", False),
        (19, "Stress & Anxiety", "How frequently do you overthink small things?", True),  # High impact
        (20, "Stress & Anxiety", "How easily do you bounce back from stress?", False),
        
        # Sleep & Energy (21-30)
        (21, "Sleep & Energy", "How restful is your sleep generally?", False),
        (22, "Sleep & Energy", "How long does it take for you to fall asleep?", False),
        (23, "Sleep & Energy", "How often do you wake up tired or exhausted?", False),
        (24, "Sleep & Energy", "How many hours of sleep do you get on average?", False),
        (25, "Sleep & Energy", "How often do you have difficulty falling asleep?", False),
        (26, "Sleep & Energy", "How do you rate your energy levels throughout the day?", False),
        (27, "Sleep & Energy", "How often do you take naps during the day due to fatigue?", False),
        (28, "Sleep & Energy", "How frequently do you sleep late due to anxiety or thoughts?", False),
        (29, "Sleep & Energy", "How consistent is your sleep schedule?", False),
        (30, "Sleep & Energy", "How much physical energy do you have for daily tasks?", False),
        
        # Social & Personal Life (31-40)
        (31, "Social & Personal Life", "How connected do you feel with your friends?", False),
        (32, "Social & Personal Life", "How often do you feel lonely?", False),
        (33, "Social & Personal Life", "How comfortable are you sharing problems with someone?", False),
        (34, "Social & Personal Life", "How often do you avoid social situations?", False),
        (35, "Social & Personal Life", "How supported do you feel by peers or mentors?", False),
        (36, "Social & Personal Life", "How often do you argue or fight with close ones?", False),
        (37, "Social & Personal Life", "How often do you isolate yourself intentionally?", False),
        (38, "Social & Personal Life", "How easily can you start or maintain conversations?", False),
        (39, "Social & Personal Life", "How meaningful are your relationships to you?", False),
        (40, "Social & Personal Life", "How comfortable are you in group settings?", False),
        
        # Motivation, Focus, & Academic Pressure (41-50)
        (41, "Motivation, Focus, & Academic Pressure", "How motivated do you feel to attend classes?", False),
        (42, "Motivation, Focus, & Academic Pressure", "How focused are you while studying?", False),
        (43, "Motivation, Focus, & Academic Pressure", "How often do you procrastinate on tasks?", False),
        (44, "Motivation, Focus, & Academic Pressure", "How confident are you about your academic performance?", False),
        (45, "Motivation, Focus, & Academic Pressure", "How often do you feel 'mentally blocked' during work?", False),
        (46, "Motivation, Focus, & Academic Pressure", "How productive do you feel in a typical week?", False),
        (47, "Motivation, Focus, & Academic Pressure", "How anxious do you feel about grades?", False),
        (48, "Motivation, Focus, & Academic Pressure", "How often do you miss deadlines or forget work?", False),
        (49, "Motivation, Focus, & Academic Pressure", "How often do you feel like giving up on tasks?", True),  # High impact
        (50, "Motivation, Focus, & Academic Pressure", "How clear are your short-term academic goals?", False)
    ]
    
    cursor.executemany(
        'INSERT INTO questions (id, dimension, question, high_impact) VALUES (?, ?, ?, ?)',
        questions_data
    )
    
    conn.commit()
    conn.close()
    print("✅ Questions populated successfully")

# Initialize resources
def populate_resources():
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    
    # Check if resources already exist
    cursor.execute('SELECT COUNT(*) FROM resources')
    if cursor.fetchone()[0] > 0:
        conn.close()
        return
    
    resources_data = [
        # Good Mental Health Resources
        ("Good", "Link", "Headspace: Daily meditation app - https://headspace.com"),
        ("Good", "Text", "Continue your current healthy habits! Try adding 10 minutes of daily gratitude journaling."),
        ("Good", "Link", "Mental wellness blogs - https://psychologytoday.com/blog"),
        ("Good", "Text", "Maintain regular exercise, good sleep, and social connections."),
        
        # Moderate Mental Health Resources
        ("Moderate", "Text", "Try the 4-7-8 breathing technique: Inhale for 4, hold for 7, exhale for 8."),
        ("Moderate", "Link", "7 Cups peer support - https://7cups.com"),
        ("Moderate", "Text", "Consider joining a student support group or academic stress workshop."),
        ("Moderate", "Link", "Calm app for meditation - https://calm.com"),
        ("Moderate", "Text", "Practice mindfulness for 10 minutes daily and limit social media before bed."),
        
        # Poor Mental Health Resources
        ("Poor", "Link", "BetterHelp online therapy - https://betterhelp.com"),
        ("Poor", "Contact", "Student counseling services - Contact your campus mental health center"),
        ("Poor", "Text", "Consider speaking with a mental health professional. You don't have to go through this alone."),
        ("Poor", "Link", "Crisis Text Line - Text HOME to 741741"),
        ("Poor", "Text", "Try creating a daily routine with small, achievable goals."),
        
        # Crisis Resources
        ("Crisis", "Contact", "National Suicide Prevention Lifeline: 988"),
        ("Crisis", "Contact", "Crisis Text Line: Text HOME to 741741"),
        ("Crisis", "Contact", "Emergency Services: 911"),
        ("Crisis", "Link", "Immediate online support - https://suicidepreventionlifeline.org"),
        ("Crisis", "Text", "You are not alone. Please reach out to someone immediately - family, friends, or emergency services."),
    ]
    
    cursor.executemany(
        'INSERT INTO resources (category, resource_type, content) VALUES (?, ?, ?)',
        resources_data
    )
    
    conn.commit()
    conn.close()
    print("✅ Resources populated successfully")

# Calculate weighted score
def calculate_score(responses):
    """Calculate inverted weighted score - higher score means better mental health"""
    high_impact_questions = [5, 9, 19, 49]  # Q5, Q9, Q19, Q49
    
    # Calculate raw score first
    raw_score = 0
    for i, response in enumerate(responses, 1):
        if i in high_impact_questions:
            raw_score += response * 1.5
        else:
            raw_score += response
    
    # Calculate maximum possible score
    # 46 normal questions (46 * 5) + 4 high-impact questions (4 * 5 * 1.5) = 230 + 30 = 260
    max_possible_score = (46 * 5) + (4 * 5 * 1.5)
    
    # Invert the score: higher score = better mental health
    inverted_score = max_possible_score - raw_score
    
    return inverted_score

# Classify mental health status
def classify_mental_health(score):
    """Classify based on inverted score thresholds - higher score = better mental health"""
    # With inverted scoring: max_score = 260, min_score = 0
    # Good: 145-260 (was previously 0-115 raw score range)
    # Moderate: 90-144 (was previously 116-170 raw score range)  
    # Poor: 0-89 (was previously 171+ raw score range)
    
    if score >= 145:
        return "Good"
    elif score >= 90:
        return "Moderate"
    else:
        return "Poor"

# API Routes
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/login')
def login():
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

@app.route('/assessment')
def assessment():
    return render_template('assessment.html')

@app.route('/results')
def results():
    return render_template('results.html')

@app.route('/test-results')
def test_results():
    with open('test_results.html', 'r') as f:
        return f.read()

@app.route('/resources')
def resources_page():
    return render_template('resources.html')

@app.route('/chat')
def chat():
    return render_template('chat.html')

@app.route('/crisis')
def crisis():
    return render_template('crisis.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/verify-email')
def verify_email():
    return render_template('verify-email.html')

@app.route('/profile')
def profile():
    return render_template('profile.html')

# API Endpoints
@app.route('/api/questions', methods=['GET'])
def get_questions():
    try:
        conn = sqlite3.connect(DATABASE_NAME)
        cursor = conn.cursor()
        
        # Check actual column names first
        cursor.execute('PRAGMA table_info(questions)')
        columns = cursor.fetchall()
        print("Database columns:", columns)
        
        # Try to get questions with the actual column names
        try:
            cursor.execute('SELECT id, dimension, question_text, order_index FROM questions ORDER BY order_index')
        except:
            # Fallback to different column names
            cursor.execute('SELECT id, dimension, question FROM questions ORDER BY id')
        
        questions = cursor.fetchall()
        conn.close()
        
        questions_list = []
        for q in questions:
            questions_list.append({
                'id': q[0],
                'dimension': q[1],
                'question': q[2],
                'high_impact': False  # Default since the current schema doesn't have this
            })
        
        return jsonify({'questions': questions_list})
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/assessment', methods=['POST'])
def process_assessment():
    try:
        data = request.get_json()
        responses = data.get('responses', [])
        
        if len(responses) != 50:
            return jsonify({'error': 'Exactly 50 responses required'}), 400
        
        # Validate response range (1-5)
        for i, response in enumerate(responses):
            if not isinstance(response, int) or response < 1 or response > 5:
                return jsonify({'error': f'Invalid response at question {i+1}. Must be 1-5'}), 400
        
        # Try ML prediction first, fallback to manual calculation
        ml_prediction = None
        ml_confidence = None
        ml_probabilities = None
        
        if model is not None and label_encoder is not None:
            try:
                # Prepare data for ML model
                import numpy as np
                input_data = np.array(responses).reshape(1, -1)
                
                # Make ML predictions
                prediction = model.predict(input_data)[0]
                probabilities = model.predict_proba(input_data)[0]
                
                # Convert prediction back to label
                ml_prediction = label_encoder.inverse_transform([prediction])[0]
                ml_confidence = float(max(probabilities))
                
                # Create probability distribution
                ml_probabilities = {}
                for i, label in enumerate(label_encoder.classes_):
                    ml_probabilities[label] = float(probabilities[i])
                
                print(f"✅ ML Prediction: {ml_prediction} (confidence: {ml_confidence:.2f})")
                
            except Exception as e:
                print(f"❌ ML prediction failed: {e}")
        
        # Calculate weighted score (fallback method)
        score = calculate_score(responses)
        fallback_classification = classify_mental_health(score)
        
        # Use ML prediction if available, otherwise use fallback
        final_classification = ml_prediction if ml_prediction else fallback_classification
        
        # Get recommendations
        conn = sqlite3.connect(DATABASE_NAME)
        cursor = conn.cursor()
        cursor.execute('SELECT resource_type, content FROM resources WHERE category = ?', (final_classification,))
        resources = cursor.fetchall()
        conn.close()
        
        recommendations = []
        for resource in resources:
            recommendations.append({
                'type': resource[0],
                'content': resource[1]
            })
        
        response_data = {
            'score': round(score, 2),
            'classification': final_classification,
            'recommendations': recommendations,
            'max_score': 260,  # Maximum possible inverted score
            'message': get_classification_message(final_classification),
            'method': 'ml' if ml_prediction else 'fallback'
        }
        
        # Add ML-specific data if available
        if ml_prediction:
            response_data.update({
                'ml_confidence': ml_confidence,
                'ml_probabilities': ml_probabilities,
                'ml_prediction': ml_prediction
            })
        
        return jsonify(response_data)
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/predict', methods=['POST'])
def predict():
    """Dedicated ML prediction endpoint following the reference pattern"""
    try:
        # Get JSON data from frontend
        data = request.get_json()
        
        # Extract responses (expecting array of 50 values)
        responses = data.get('responses', [])
        
        if len(responses) != 50:
            return jsonify({'error': 'Expected 50 responses'}), 400
        
        # Validate response range (1-5)
        for i, response in enumerate(responses):
            if not isinstance(response, int) or response < 1 or response > 5:
                return jsonify({'error': f'Invalid response at question {i+1}. Must be 1-5'}), 400
        
        if model is None or label_encoder is None:
            return jsonify({'error': 'ML models not loaded', 'status': 'error'}), 500
        
        # Convert to numpy array and reshape for prediction
        import numpy as np
        input_data = np.array(responses).reshape(1, -1)
        
        # Make predictions
        prediction = model.predict(input_data)[0]
        probabilities = model.predict_proba(input_data)[0]
        
        # Convert prediction back to label
        predicted_label = label_encoder.inverse_transform([prediction])[0]
        
        # Get confidence (highest probability)
        confidence = float(max(probabilities))
        
        # Create probability distribution
        prob_dict = {}
        for i, label in enumerate(label_encoder.classes_):
            prob_dict[label] = float(probabilities[i])
        
        # Return results
        return jsonify({
            'prediction': predicted_label,
            'confidence': confidence,
            'probabilities': prob_dict,
            'status': 'success'
        })
        
    except Exception as e:
        return jsonify({'error': str(e), 'status': 'error'}), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint to verify model status"""
    return jsonify({
        'status': 'healthy', 
        'model_loaded': model is not None,
        'label_encoder_loaded': label_encoder is not None,
        'app_name': 'Manahstiti Mental Health Assessment'
    })

@app.route('/api/resources', methods=['POST'])
def get_resources():
    try:
        data = request.get_json()
        category = data.get('category', 'Good')
        
        conn = sqlite3.connect(DATABASE_NAME)
        cursor = conn.cursor()
        cursor.execute('SELECT resource_type, content FROM resources WHERE category = ?', (category,))
        resources = cursor.fetchall()
        conn.close()
        
        resources_list = []
        for resource in resources:
            resources_list.append({
                'type': resource[0],
                'content': resource[1]
            })
        
        return jsonify({'resources': resources_list})
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/crisis-support', methods=['GET'])
def get_crisis_support():
    try:
        conn = sqlite3.connect(DATABASE_NAME)
        cursor = conn.cursor()
        cursor.execute('SELECT resource_type, content FROM resources WHERE category = ?', ('Crisis',))
        resources = cursor.fetchall()
        conn.close()
        
        crisis_resources = []
        for resource in resources:
            crisis_resources.append({
                'type': resource[0],
                'content': resource[1]
            })
        
        return jsonify({'crisis_resources': crisis_resources})
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/chatbot', methods=['POST'])
def chat_with_ai():
    try:
        print("🔍 Chatbot endpoint called!")
        data = request.get_json()
        user_message = data.get('message', '').strip()
        user_id = data.get('user_id', 'default_user')  # Allow custom user_id or use default
        print(f"🔍 User message: {user_message}")
        print(f"🔍 User ID: {user_id}")
        
        if not user_message:
            return jsonify({'error': 'Message is required'}), 400
        
        # Get chat history for this user
        chat_history = get_chat_history(user_id)
        print(f"🔍 Found {len(chat_history)} previous conversations")
        
        # Create conversation context from history
        conversation_context = create_conversation_context(chat_history)
        
        # Prepare system prompt with conversation history
        system_prompt = {
            'role': 'system',
            'content': f'''You are a caring AI friend named Manahstiti, designed to provide emotional support to students. 
            You are empathetic, understanding, and focused on mental health support. Keep responses encouraging, 
            supportive, and helpful. Avoid giving medical advice but offer coping strategies, listening ear, 
            and gentle guidance. Remember you're talking to students who may be stressed about academics, 
            relationships, or personal issues. Always be kind and supportive.{conversation_context}'''
        }
        
        # Create messages array with system prompt and current user message
        messages = [
            system_prompt,
            {'role': 'user', 'content': user_message}
        ]
        
        # Call Groq API
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {GROQ_API_KEY}'
        }
        
        payload = {
            'model': GROQ_MODEL,
            'messages': messages,
            'max_tokens': 300,
            'temperature': 0.7
        }
        
        print(f"🔍 Making Groq API call...")
        response = requests.post(GROQ_API_URL, headers=headers, json=payload, timeout=30)
        
        print(f"🔍 Groq API response status: {response.status_code}")
        
        if response.status_code == 200:
            ai_response = response.json()['choices'][0]['message']['content']
            
            # Store conversation in JSON memory
            memory_stored = store_conversation(user_id, user_message, ai_response)
            
            return jsonify({
                'response': ai_response,
                'status': 'success',
                'memory_stored': memory_stored,
                'conversations_in_history': len(chat_history)
            })
        else:
            # Fallback response if Groq API fails
            fallback_responses = [
                "I'm here to listen. Can you tell me more about what's bothering you?",
                "That sounds challenging. Remember, it's okay to feel this way, and you're not alone.",
                "I understand you're going through a tough time. What usually helps you feel better?",
                "Thank you for sharing with me. Your feelings are valid, and it's brave of you to reach out."
            ]
            
            import random
            fallback_response = random.choice(fallback_responses)
            
            return jsonify({
                'response': fallback_response,
                'status': 'fallback',
                'message': 'AI service temporarily unavailable, but I\'m still here for you!'
            })
    
    except Exception as e:
        return jsonify({
            'response': "I'm having trouble responding right now, but I want you to know that I care about you. Please reach out to someone you trust if you need immediate support.",
            'status': 'error',
            'message': 'Connection error'
        }), 500

@app.route('/api/memory/stats', methods=['GET'])
def get_memory_stats():
    """Get memory statistics for current user"""
    try:
        user_id = get_user_id()
        chat_history = get_chat_history(user_id)
        
        return jsonify({
            'total_conversations': len(chat_history),
            'user_id': user_id,
            'status': 'success'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/memory/clear', methods=['POST'])
def clear_user_memories():
    """Clear all memories for current user"""
    try:
        data = request.get_json()
        user_id = data.get('user_id', 'default_user')
        
        # Load memories and remove this user's data
        memories = load_chat_memories()
        deleted_count = len(memories.get(user_id, []))
        
        if user_id in memories:
            del memories[user_id]
            save_chat_memories(memories)
        
        return jsonify({
            'deleted_conversations': deleted_count,
            'status': 'success',
            'message': f'Cleared {deleted_count} conversations for user'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/memory/clear-all', methods=['POST'])
def clear_all_memories():
    """Clear the entire JSON file (all users)"""
    try:
        cleared = clear_json_after_chat()
        
        return jsonify({
            'status': 'success',
            'memory_cleared': cleared,
            'message': 'All conversation memories cleared'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def get_classification_message(classification):
    messages = {
        'Good': 'Great job! Your mental health appears to be in good shape. Keep up the positive habits!',
        'Moderate': 'You might be experiencing some challenges. Consider trying some coping strategies and don\'t hesitate to seek support.',
        'Poor': 'It looks like you\'re going through a difficult time. Please consider reaching out to a mental health professional or trusted person for support.'
    }
    return messages.get(classification, 'Assessment completed.')

# Initialize everything
if __name__ == '__main__':
    print("🚀 Initializing Manahstiti...")
    init_db()
    populate_questions()
    populate_resources()
    
    print("✅ Simple JSON memory system ready!")
    print("✅ Manahstiti backend ready!")
    app.run(debug=os.environ.get('FLASK_DEBUG', 'True').lower() == 'true', host=HOST, port=PORT) 