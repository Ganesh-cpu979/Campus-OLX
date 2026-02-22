import streamlit as st
import psycopg2
import hashlib
import time
import re
import uuid
import random
import string
import smtplib
import ssl
import base64
from email.message import EmailMessage
from datetime import datetime
from streamlit_option_menu import option_menu

# --- CONFIGURATION (User must fill this) ---
SENDER_EMAIL = "ganeshjanapuri@gmail.com"  
SENDER_PASSWORD = "bofd bzua sgau kzyv"  

# ----------------------------------------------------
# 1. DATABASE SETUP (CLOUD POSTGRESQL)
# ----------------------------------------------------
# Streamlit secrets se URL uthayega
try:
    DB_URL = st.secrets["DB_URL"]
except:
    st.error("⚠️ Database connection string (DB_URL) not found in Streamlit Secrets!")
    st.stop()

def get_db_connection():
    return psycopg2.connect(DB_URL)

def make_hashes(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def run_query(query, params=()):
    with get_db_connection() as conn:
        with conn.cursor() as c:
            c.execute(query, params)
            conn.commit()

def get_data(query, params=()):
    with get_db_connection() as conn:
        with conn.cursor() as c:
            c.execute(query, params)
            return c.fetchall()

def get_single_data(query, params=()):
    with get_db_connection() as conn:
        with conn.cursor() as c:
            c.execute(query, params)
            return c.fetchone()

def init_db():
    run_query('CREATE TABLE IF NOT EXISTS userstable(username TEXT PRIMARY KEY, fullname TEXT, password TEXT, course TEXT, year TEXT, id_card_path TEXT, status TEXT, email TEXT)')
    run_query('CREATE TABLE IF NOT EXISTS productstable(id SERIAL PRIMARY KEY, seller_name TEXT, product_name TEXT, product_cat TEXT, product_price TEXT, product_desc TEXT, product_img TEXT, type TEXT, status TEXT)')
    run_query('CREATE TABLE IF NOT EXISTS messages(sender TEXT, receiver TEXT, message TEXT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    run_query('CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, username TEXT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    run_query('CREATE TABLE IF NOT EXISTS middleman_emails(email TEXT PRIMARY KEY, registered INTEGER DEFAULT 0)')
    run_query('CREATE TABLE IF NOT EXISTS help_tickets(id SERIAL PRIMARY KEY, username TEXT, issue TEXT, image_path TEXT, status TEXT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    
    try: run_query('ALTER TABLE help_tickets ADD COLUMN image_path TEXT')
    except: pass

    try:
        run_query('INSERT INTO userstable(username, fullname, password, status) VALUES (%s,%s,%s,%s)', 
                  ('admin', 'Administrator', make_hashes('admin123'), 'admin'))
    except: pass

# --- DB Helper Functions (Using %s for Postgres) ---
def is_username_taken(username):
    if not username: return False
    res = get_single_data("SELECT username FROM userstable WHERE LOWER(username)=LOWER(%s)", (username.strip(),))
    return res is not None

def is_email_taken(email):
    if not email: return False
    res = get_single_data("SELECT email FROM userstable WHERE LOWER(email)=LOWER(%s)", (email.strip(),))
    return res is not None

def login_user(username, password):
    return get_data('SELECT * FROM userstable WHERE username=%s AND password=%s', (username.strip(), password))

def get_user_details(username):
    return get_single_data('SELECT * FROM userstable WHERE username=%s', (username,))

def update_password(username, new_password):
    run_query('UPDATE userstable SET password=%s WHERE username=%s', (make_hashes(new_password), username))

def add_userdata(username, fullname, password, course, year, id_card_path, email, status='pending'):
    run_query('INSERT INTO userstable(username,fullname,password,course,year,id_card_path,status,email) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)', 
              (username.strip(), fullname.strip(), password, course, year, id_card_path, status, email.strip()))

def add_product(seller_name, name, cat, price, desc, img, p_type, status='pending'):
    run_query('INSERT INTO productstable(seller_name, product_name, product_cat, product_price, product_desc, product_img, type, status) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)', 
              (seller_name, name, cat, price, desc, img, p_type, status))

def mark_product_sold(pid):
    run_query("UPDATE productstable SET status='Sold' WHERE id=%s", (pid,))

def get_all_middlemen():
    return get_data("SELECT * FROM userstable WHERE status='middleman'")

def add_middleman_email(email):
    try: run_query("INSERT INTO middleman_emails(email) VALUES (%s)", (email.strip(),))
    except: pass

def check_middleman_email(email):
    return get_single_data("SELECT registered FROM middleman_emails WHERE email=%s", (email.strip(),))

def register_middleman_email(email):
    run_query("UPDATE middleman_emails SET registered=1 WHERE email=%s", (email.strip(),))

def create_help_ticket(username, issue, image_path=None):
    run_query("INSERT INTO help_tickets(username, issue, image_path, status) VALUES (%s, %s, %s, 'pending')", (username, issue, image_path))

def get_pending_tickets():
    return get_data("SELECT * FROM help_tickets WHERE status='pending' ORDER BY timestamp DESC")

def resolve_ticket(ticket_id):
    run_query("UPDATE help_tickets SET status='resolved' WHERE id=%s", (ticket_id,))

def get_my_tickets(username):
    return get_data("SELECT * FROM help_tickets WHERE username=%s ORDER BY timestamp DESC", (username,))

def create_session(username):
    token = str(uuid.uuid4())
    run_query('INSERT INTO sessions(token, username) VALUES (%s,%s)', (token, username))
    return token

def validate_session(token):
    data = get_single_data('SELECT username FROM sessions WHERE token=%s', (token,))
    return data[0] if data else None

def delete_session(token):
    run_query('DELETE FROM sessions WHERE token=%s', (token,))

def generate_otp():
    return ''.join(random.choices(string.digits, k=6))

def send_otp_email(receiver_email, otp, subject="Campus OLX - OTP"):
    msg = EmailMessage()
    msg.set_content(f"Your OTP is: {otp}\n\nDo not share this with anyone.")
    msg['Subject'] = subject
    msg['From'] = SENDER_EMAIL
    msg['To'] = receiver_email
    context = ssl.create_default_context()
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.send_message(msg)
        return True, "✅ OTP Sent Successfully! Check your Inbox."
    except Exception as e:
        return False, f"❌ Failed to send email: {e}"

# --- CLOUD PROOF IMAGE HANDLING (BASE64) ---
def save_uploaded_file(f, folder):
    bytes_data = f.getvalue()
    base64_str = base64.b64encode(bytes_data).decode()
    return f"data:{f.type};base64,{base64_str}"

def render_image(img_string, **kwargs):
    if img_string and img_string.startswith('data:image'):
        img_data = img_string.split(',')[1]
        st.image(base64.b64decode(img_data), **kwargs)
    elif img_string:
        st.image(img_string, **kwargs)
    else:
        st.write("📷 No Image")

def send_message(sender, receiver, msg):
    run_query('INSERT INTO messages(sender, receiver, message) VALUES (%s,%s,%s)', (sender, receiver, msg))

def get_messages(user1, user2):
    return get_data('''SELECT * FROM messages 
                       WHERE (sender=%s AND receiver=%s) OR (sender=%s AND receiver=%s) 
                       ORDER BY timestamp ASC''', (user1, user2, user2, user1))

def get_all_chat_partners(user):
    sent = get_data("SELECT DISTINCT receiver FROM messages WHERE sender=%s", (user,))
    received = get_data("SELECT DISTINCT sender FROM messages WHERE receiver=%s", (user,))
    return list(set([x[0] for x in sent] + [x[0] for x in received]))

# ----------------------------------------------------
# 2. APP INITIALIZATION & ADVANCED UI STYLES (HTML/CSS)
# ----------------------------------------------------
st.set_page_config(page_title="Campus OLX", page_icon="🎓", layout="wide")
init_db()

# ADVANCED CUSTOM CSS INJECTION - FULLY OPTIMIZED
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;600;700&display=swap');
    html, body, [class*="css"] { font-family: 'Poppins', sans-serif !important; }
    
    .stApp {
        background-image: linear-gradient(rgba(0, 0, 0, 0.75), rgba(0, 0, 0, 0.75)), url("https://images.unsplash.com/photo-1497366216548-37526070297c?q=80&w=2000&auto=format&fit=crop");
        background-attachment: fixed; background-size: cover; background-position: center;
    }

    div[data-testid="stForm"], div[data-testid="stContainer"], section[data-testid="stSidebar"] {
        background: rgba(30, 30, 30, 0.4) !important; backdrop-filter: blur(12px);
        border-radius: 15px; box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.3);
        border: 1px solid rgba(255, 255, 255, 0.1); padding: 20px;
    }
    
    .stMarkdown p, label[data-testid="stWidgetLabel"] p, .stCheckbox p, .stRadio p, div[data-testid="stMarkdownContainer"] p {
        color: #e2e8f0 !important; font-weight: 500;
    }

    div[data-testid="stExpander"] details summary p { color: #ffffff !important; font-weight: 600 !important; font-size: 1.1rem; }
    
    h1, h2, h3, h4 { 
        background: -webkit-linear-gradient(45deg, #4facfe, #00f2fe);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        font-weight: 700 !important; text-shadow: none !important; padding-bottom: 5px;
    }

    .stTextInput>div>div>input, .stSelectbox>div>div>select, .stTextArea>div>div>textarea {
        border-radius: 10px; border: 1px solid rgba(255,255,255,0.2);
        background-color: rgba(255, 255, 255, 0.9) !important; color: #1a1a1a !important; 
    }
    
    .stTextInput>div>div>input:focus, .stSelectbox>div>div>select:focus, .stTextArea>div>div>textarea:focus {
        border-color: #4facfe; box-shadow: 0 0 0 3px rgba(79, 172, 254, 0.3);
    }

    .product-card {
        background: rgba(255, 255, 255, 0.1); padding: 15px; border-radius: 15px; text-align: center;
        border: 1px solid rgba(255,255,255,0.1); backdrop-filter: blur(5px); transition: all 0.3s ease; height: 100%;
    }
    .product-card p, .product-card h3, .product-card span, .product-card div { color: #ffffff !important; }
    .product-card h2 { -webkit-text-fill-color: #00E676 !important; }
    .product-card:hover { transform: translateY(-5px); border-color: #4facfe; box-shadow: 0 10px 20px rgba(0,0,0,0.4); }

    .stButton > button, div[data-testid="stFormSubmitButton"] > button {
        background: linear-gradient(45deg, #4facfe 0%, #00f2fe 100%) !important; border: none !important;
        border-radius: 30px !important; padding: 10px 20px !important; transition: all 0.3s ease !important;
        box-shadow: 0 4px 15px rgba(0, 242, 254, 0.3) !important;
    }
    
    .stButton > button p, div[data-testid="stFormSubmitButton"] > button p, .stButton > button *, div[data-testid="stFormSubmitButton"] > button * {
        color: #121212 !important; font-weight: 700 !important; font-size: 16px !important;
    }

    .stButton > button:hover, div[data-testid="stFormSubmitButton"] > button:hover {
        transform: translateY(-2px) !important; box-shadow: 0 6px 20px rgba(0, 242, 254, 0.6) !important;
    }
</style>
""", unsafe_allow_html=True)

if 'user' not in st.session_state: st.session_state['user'] = None
if 'role' not in st.session_state: st.session_state['role'] = None
if 'signup_step' not in st.session_state: st.session_state.signup_step = 1
if 'signup_data' not in st.session_state: st.session_state.signup_data = {}
if 'forgot_step' not in st.session_state: st.session_state.forgot_step = 1

if not st.session_state['user']:
    token = st.query_params.get('token')
    if token:
        username = validate_session(token)
        if username:
            st.session_state['user'] = username
            u_data = get_user_details(username)
            if u_data:
                role = 'admin' if u_data[6] == 'admin' else ('middleman' if u_data[6] == 'middleman' else 'student')
                st.session_state['role'] = role
        else: st.query_params.clear()

with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3135/3135715.png", width=100)
    st.markdown("<h2 style='text-align: center;'>Campus OLX</h2>", unsafe_allow_html=True)
    st.markdown("---")
    
    if st.session_state['user']:
        st.success(f"Hello, {st.session_state['user']}! 👋")
        role = st.session_state['role']
        
        if role == 'admin':
            menu = ["Dashboard", "Users", "Products", "Middlemen", "Issues"]
            icons = ['speedometer2', 'people', 'box-seam', 'person-badge', 'check-square']
        elif role == 'middleman':
            menu = ["Sell Item", "Inbox", "Help", "Profile"]
            icons = ['plus-circle', 'chat-dots', 'question-circle', 'person']
        else: 
            menu = ["Marketplace", "Handover to Middleman", "Inbox", "Help", "Profile"] 
            icons = ['shop', 'box-arrow-right', 'chat-dots', 'question-circle', 'person']
            
        choice = option_menu("Menu", menu, icons=icons, default_index=0)
        st.markdown("---")
        if st.button("Logout 🚪", use_container_width=True):
            token = st.query_params.get('token')
            if token: delete_session(token)
            st.query_params.clear()
            st.session_state['user'] = None; st.session_state['role'] = None; st.rerun()
    else:
        # === NAYE MENUS (ABOUT US & HOW TO USE) YAHAN ADD HAIN ===
        choice = option_menu("Welcome", 
                             ["Login", "Student Sign Up", "Middle Man Login", "Middle Man Sign Up", "How to Use", "About Us"], 
                             icons=['box-arrow-in-right', 'person-plus', 'box-arrow-in-right', 'person-plus', 'book', 'info-circle'], 
                             default_index=0)

if not st.session_state['user']:
    if choice == "Login":
        log_type = st.radio("Select Option", ["Login", "Forgot Password"], horizontal=True)
        if log_type == "Login":
            st.markdown("<h1>🔑 Welcome Back</h1>", unsafe_allow_html=True)
            with st.form("login_form"):
                username = st.text_input("Roll Number / Admin ID").strip()
                password = st.text_input("Password", type='password')
                if st.form_submit_button("Login Securely"):
                    result = login_user(username, make_hashes(password))
                    if result:
                        u_data = result[0]
                        if u_data[6] in ['admin', 'approved', 'middleman']:
                            st.session_state['user'] = username
                            st.session_state['role'] = 'admin' if u_data[6] == 'admin' else ('middleman' if u_data[6] == 'middleman' else 'student')
                            st.query_params['token'] = create_session(username)
                            st.rerun()
                        else: st.warning(f"Account Status: {u_data[6]}")
                    else: st.error("❌ Invalid Credentials")
                    
        else: 
            st.markdown("<h1>🔓 Forgot Password</h1>", unsafe_allow_html=True)
            if st.session_state.forgot_step == 1:
                f_roll = st.text_input("Enter your Roll Number").strip()
                if st.button("Send OTP to Registered Email"):
                    u_data = get_user_details(f_roll)
                    if u_data and u_data[7]:
                        st.session_state.forgot_email = u_data[7]
                        st.session_state.forgot_user = f_roll
                        st.session_state.forgot_otp = generate_otp()
                        with st.spinner("Sending OTP..."):
                            send_otp_email(st.session_state.forgot_email, st.session_state.forgot_otp, "Campus OLX - Password Reset")
                        st.session_state.forgot_step = 2
                        st.rerun()
                    else: st.error("Roll Number not found or no email associated.")
                        
            elif st.session_state.forgot_step == 2:
                st.info(f"OTP sent to masked email: {st.session_state.forgot_email[:3]}***@***")
                entered_otp = st.text_input("Enter OTP").strip()
                if st.button("Verify OTP"):
                    if entered_otp == st.session_state.forgot_otp:
                        st.session_state.forgot_step = 3
                        st.rerun()
                    else: st.error("Invalid OTP")
                if st.button("Cancel"): st.session_state.forgot_step = 1; st.rerun()
                
            elif st.session_state.forgot_step == 3:
                new_pwd = st.text_input("Enter New Password", type='password')
                new_pwd2 = st.text_input("Confirm New Password", type='password')
                if st.button("Reset Password"):
                    if len(new_pwd) < 8: st.error("Password must be at least 8 characters")
                    elif new_pwd == new_pwd2:
                        update_password(st.session_state.forgot_user, new_pwd)
                        st.success("Password Updated Successfully! Please Login.")
                        st.session_state.forgot_step = 1
                        time.sleep(2)
                        st.rerun()
                    else: st.error("Passwords do not match")

    elif choice == "Student Sign Up":
        st.markdown("<h1 style='text-align:center;'>📝 Student Registration</h1>", unsafe_allow_html=True)
        if st.session_state.signup_step == 1:
            st.info("Step 1: College Identity")
            c1, c2 = st.columns(2)
            with c1:
                full_name = st.text_input("Full Name").strip()
                username = st.text_input("Roll Number").strip()
                id_front = st.file_uploader("Upload ID Card Photo", type=['jpg', 'png'])
            with c2:
                course = st.selectbox("Branch", ["CSE", "ECE", "EEE", "Civil", "Mechanical", "Other"])
                year = st.selectbox("Year", ["Diploma 1st Year", "Diploma 2nd Year", "Diploma 3rd Year", "B.Tech 1st Year", "B.Tech 2nd Year", "B.Tech 3rd Year", "B.Tech 4th Year"])
            
            if st.button("Proceed to Next Step ➡️"):
                if not all([full_name, username, id_front]): st.error("Please fill all fields and upload ID.")
                elif is_username_taken(username): st.error("❌ Roll Number already registered!")
                else:
                    path = save_uploaded_file(id_front, "id_cards")
                    st.session_state.signup_data = { "username": username, "fullname": full_name, "course": course, "year": year, "id_card_path": path }
                    st.session_state.signup_step = 2
                    st.rerun()

        elif st.session_state.signup_step == 2:
            st.info("Step 2: Security & Verification")
            email = st.text_input("College or Personal Email").strip()
            
            col1, col2 = st.columns([1,1])
            with col1:
                if st.button("Send Verification OTP"):
                    if not re.match(r"[^@]+@[^@]+\.[^@]+", email): st.error("Invalid Email")
                    elif is_email_taken(email): st.error("❌ Email already in use!")
                    else:
                        st.session_state.signup_data['email'] = email
                        st.session_state.signup_otp = generate_otp()
                        with st.spinner("Sending OTP securely..."):
                            send_otp_email(email, st.session_state.signup_otp)
                        st.success("OTP Sent!")
            with col2:
                otp_input = st.text_input("Enter OTP sent to email").strip()
            
            password = st.text_input("Setup Password", type='password')
            
            c3, c4 = st.columns(2)
            if c3.button("⬅️ Go Back"): st.session_state.signup_step = 1; st.rerun()
            if c4.button("Verify & Continue ➡️"):
                if 'signup_otp' not in st.session_state or otp_input != st.session_state.signup_otp: st.error("❌ Incorrect or missing OTP")
                elif len(password) < 8: st.error("Password must be 8+ chars")
                else:
                    st.session_state.signup_data['password'] = make_hashes(password)
                    st.session_state.signup_step = 3
                    st.rerun()

        elif st.session_state.signup_step == 3:
            st.info("Step 3: Terms & Conditions")
            st.markdown("1. **Campus Use Only**: Strictly for students.\n2. **No Illegal Items**: Selling prohibited items is an offense.\n3. **Behave Professionally**: Spamming will result in ban.")
            agree = st.checkbox("I agree to the Terms and Conditions")
            c1, c2 = st.columns(2)
            if c1.button("⬅️ Back"): st.session_state.signup_step = 2; st.rerun()
            if c2.button("Create Account ✅", type="primary"):
                if agree:
                    d = st.session_state.signup_data
                    add_userdata(d['username'], d['fullname'], d['password'], d['course'], d['year'], d['id_card_path'], d['email'], 'pending')
                    st.balloons()
                    st.success("✅ Account created! Waiting for Admin Approval.")
                    st.session_state.signup_step = 1; st.session_state.signup_data = {}
                    time.sleep(2); st.rerun()
                else: st.error("You must agree to T&C.")

    elif choice == "Middle Man Login":
        st.markdown("<h1>🤝 Middle Man Login</h1>", unsafe_allow_html=True)
        with st.form("mm_login"):
            username = st.text_input("Middle Man Username/ID").strip()
            password = st.text_input("Password", type='password')
            if st.form_submit_button("Login to Dashboard"):
                res = login_user(username, make_hashes(password))
                if res and res[0][6] == 'middleman':
                    st.session_state['user'] = username; st.session_state['role'] = 'middleman'
                    st.query_params['token'] = create_session(username)
                    st.rerun()
                else: st.error("❌ Invalid Middle Man Credentials")

    elif choice == "Middle Man Sign Up":
        st.markdown("<h1>🤝 Middle Man Registration</h1>", unsafe_allow_html=True)
        st.write("You can only register if Admin has pre-approved your email.")
        if 'mm_verified' not in st.session_state: st.session_state.mm_verified = False
        
        email = st.text_input("Enter your Official Email Address").strip()
        if st.button("Check Eligibility"):
            status = check_middleman_email(email)
            if status is None: st.error("❌ Email not authorized by Admin.")
            elif status[0] == 1: st.error("❌ This email is already registered.")
            else:
                st.success("✅ Email Authorized! Please setup your profile.")
                st.session_state.mm_verified = True; st.session_state.mm_email = email
                
        if st.session_state.mm_verified:
            with st.form("mm_setup"):
                mm_name = st.text_input("Full Name").strip()
                mm_user = st.text_input("Choose a Username (No spaces)").strip()
                mm_pwd = st.text_input("Setup Password", type='password')
                if st.form_submit_button("Complete Registration"):
                    if is_username_taken(mm_user): st.error("Username taken!")
                    elif len(mm_pwd) < 6: st.error("Password too short.")
                    else:
                        add_userdata(mm_user, mm_name, make_hashes(mm_pwd), "N/A", "N/A", "N/A", st.session_state.mm_email, 'middleman')
                        register_middleman_email(st.session_state.mm_email)
                        st.success("✅ Registered Successfully! Please Login.")
                        st.session_state.mm_verified = False

    # ====== HOW TO USE ======
    elif choice == "How to Use":
        st.markdown("<h1 style='text-align:center;'>📖 How to Use Campus OLX</h1>", unsafe_allow_html=True)
        st.markdown("""
        <div style="background: rgba(30, 30, 30, 0.4); backdrop-filter: blur(12px); border-radius: 15px; padding: 30px; border: 1px solid rgba(255,255,255,0.1); margin-top: 20px;">
            <h3 style="color: #4facfe;">🎓 For Students</h3>
            <ol style="color: #e2e8f0; line-height: 1.8; font-size: 16px;">
                <li><b>Sign Up:</b> Register using your College Roll Number and official email. Upload your ID card for verification.</li>
                <li><b>Wait for Approval:</b> The Admin will securely verify your identity and approve your account.</li>
                <li><b>Buy Items:</b> Browse the student marketplace. If you need an item, click "Contact Seller" to directly message the Middleman handling it.</li>
                <li><b>Sell Items:</b> Navigate to "Handover to Middleman". Select an active Middleman from the list and send them your item details. They will collect the item from you and post it online.</li>
            </ol>
            <br>
            <h3 style="color: #00f2fe;">🤝 For Middlemen</h3>
            <ol style="color: #e2e8f0; line-height: 1.8; font-size: 16px;">
                <li><b>Get Authorized:</b> You cannot sign up directly. The Admin must pre-approve your email address first.</li>
                <li><b>Post Items:</b> Once a student hands over an item, log in, take a photo, and list it in the "Sell Item" section.</li>
                <li><b>Handle Deals:</b> Negotiate and chat with interested buyers in your "Inbox". Once a physical deal is done, click "Mark as Sold" to update the marketplace.</li>
            </ol>
            <br>
            <h3 style="color: #4facfe;">🛠️ General Help</h3>
            <ul style="color: #e2e8f0; line-height: 1.8; font-size: 16px;">
                <li>Use the <b>Help & Support</b> tab inside your dashboard to send a direct issue ticket (with screenshots) to the Admin.</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)

    # ====== ABOUT US ======
    elif choice == "About Us":
        st.markdown("<h1 style='text-align:center;'>ℹ️ About Us</h1>", unsafe_allow_html=True)
        st.markdown("""
        <div style="background: rgba(30, 30, 30, 0.4); backdrop-filter: blur(12px); border-radius: 15px; padding: 30px; border: 1px solid rgba(255,255,255,0.1); margin-top: 20px;">
            <h3 style="color: #4facfe;">🌟 Our Vision</h3>
            <p style="color: #e2e8f0; font-size: 16px; line-height: 1.6;">
                To build a seamless, secure, and sustainable localized marketplace that connects students within the campus, making academic resources accessible and affordable for everyone.
            </p>
            <br>
            <h3 style="color: #00f2fe;">🚀 Our Mission</h3>
            <p style="color: #e2e8f0; font-size: 16px; line-height: 1.6;">
                To empower the student community by providing a dedicated platform to easily exchange pre-owned books, electronics, drafters, and stationery. We aim to reduce waste, save money, and foster a strong culture of mutual support among engineering and diploma peers.
            </p>
            <br>
            <h3 style="color: #4facfe;">👨‍💻 Developed By</h3>
            <p style="color: #e2e8f0; font-size: 16px; margin-bottom: 5px;">This project is proudly designed and developed by:</p>
            <ul style="color: #e2e8f0; font-size: 16px; line-height: 1.8;">
                <li><b>Ganesh</b> <span style="color:#00f2fe;">(Team Lead)</span></li>
                <li><b>Siaram</b></li>
                <li><b>Navyasri</b></li>
                <li><b>Akshitya</b></li>
                <li><b>Mrigank</b></li>
                <li><b>Manish</b></li>
            </ul>
        </div>
        """, unsafe_allow_html=True)

else:
    if st.session_state['role'] == 'student':
        if choice == "Marketplace":
            st.markdown("<h1>🛒 Student Marketplace</h1>", unsafe_allow_html=True)
            c1, c2, c3 = st.columns(3)
            search = c1.text_input("🔍 Search Item...")
            cat_filter = c2.selectbox("Filter Category", ["All", "Books", "Electronics", "Stationery", "Other"])
            sort_by = c3.selectbox("Sort By", ["Latest", "Price: Low to High", "Price: High to Low"])
            st.divider()
            
            all_prods = get_data("SELECT * FROM productstable WHERE status='approved'")
            if search: all_prods = [p for p in all_prods if search.lower() in p[2].lower()]
            if cat_filter != "All": all_prods = [p for p in all_prods if p[3] == cat_filter]
            if sort_by == "Price: Low to High": all_prods = sorted(all_prods, key=lambda x: float(x[4]))
            elif sort_by == "Price: High to Low": all_prods = sorted(all_prods, key=lambda x: float(x[4]), reverse=True)
                
            if not all_prods: st.info("No items found matching your criteria.")
            cols = st.columns(4)
            for i, p in enumerate(all_prods):
                with cols[i%4]:
                    st.markdown("<div class='product-card'>", unsafe_allow_html=True)
                    render_image(p[6], use_container_width=True)
                    st.markdown(f"<h3>{p[2]}</h3>", unsafe_allow_html=True)
                    st.markdown(f"<h2 style='color:#00E676; margin:0; -webkit-text-fill-color: #00E676;'>₹{p[4]}</h2>", unsafe_allow_html=True)
                    st.caption(f"Category: {p[3]}")
                    st.caption(f"Posted by: {p[1]}")
                    if st.button(f"Contact Seller", key=f"buy_{p[0]}", use_container_width=True):
                        send_message(st.session_state['user'], p[1], f"Hi, I want to buy your item: **{p[2]}** (₹{p[4]}). Is it available?")
                        st.success("Message sent to Middleman! Check your Inbox.")
                    st.markdown("</div><br>", unsafe_allow_html=True)

        elif choice == "Handover to Middleman":
            st.markdown("<h1>📦 Sell Item (Handover)</h1>", unsafe_allow_html=True)
            st.info("To sell an item, contact a Middleman. They will collect the item and post it on the marketplace for you.")
            m_men = get_all_middlemen()
            if not m_men: st.warning("No Middlemen available currently.")
            else:
                mm_list = [f"{m[1]} (@{m[0]})" for m in m_men]
                selected_mm = st.selectbox("Select a Middleman to contact", mm_list)
                mm_username = selected_mm.split("(@")[1].replace(")", "")
                with st.form("handover_form"):
                    item_name = st.text_input("What do you want to sell?")
                    expected_price = st.text_input("Expected Price (₹)")
                    details = st.text_area("Item Details & Your Hostel/Room No. for pickup")
                    if st.form_submit_button("Send Request to Middleman"):
                        if item_name and expected_price:
                            send_message(st.session_state['user'], mm_username, f"HANDOVER REQUEST\nItem: {item_name}\nExpected Price: ₹{expected_price}\nDetails: {details}")
                            st.success(f"Request sent to {mm_username}! Check Inbox for their reply.")
                        else: st.error("Fill mandatory fields.")

        elif choice == "Inbox":
            st.markdown("<h1>💬 Your Inbox</h1>", unsafe_allow_html=True)
            partners = get_all_chat_partners(st.session_state['user'])
            if 'admin' in partners: partners.remove('admin')
            if not partners: st.info("No messages yet.")
            else:
                active_chat = st.selectbox("Select Chat", partners)
                st.divider()
                msgs = get_messages(st.session_state['user'], active_chat)
                for m in msgs:
                    align = "right" if m[0] == st.session_state['user'] else "left"
                    bg_color = 'linear-gradient(135deg, #a8edea 0%, #fed6e3 100%)' if align=='right' else '#f1f0f0'
                    st.markdown(f"<div style='text-align: {align}; padding: 12px 18px; border-radius: 20px; background: {bg_color}; color: #333; margin: 8px 0; display: inline-block; max-width: 80%; box-shadow: 0 4px 6px rgba(0,0,0,0.05);'><b>{m[0]}</b><br>{m[2]}</div>", unsafe_allow_html=True)
                with st.form("send_msg", clear_on_submit=True):
                    new_msg = st.text_input("Type your message here...")
                    if st.form_submit_button("Send Message 🚀"):
                        if new_msg:
                            send_message(st.session_state['user'], active_chat, new_msg); st.rerun()

        elif choice == "Help":
            st.markdown("<h1>🆘 Help & Support</h1>", unsafe_allow_html=True)
            with st.form("report_issue", clear_on_submit=True):
                issue_text = st.text_area("Describe your issue in detail...")
                screenshot = st.file_uploader("Attach Screenshot (Optional)", type=['png', 'jpg', 'jpeg'])
                if st.form_submit_button("Submit Issue Ticket"):
                    if issue_text:
                        img_path = save_uploaded_file(screenshot, "help_screenshots") if screenshot else None
                        create_help_ticket(st.session_state['user'], issue_text, img_path)
                        st.success("Ticket Created! Admin will review it shortly.")
                        time.sleep(1); st.rerun()
                    else: st.error("Please enter issue details.")
            st.divider()
            st.write("### Your Reported Issues")
            my_tickets = get_my_tickets(st.session_state['user'])
            if my_tickets:
                for t in my_tickets:
                    status_color = "#ff4444" if t[4] == "pending" else "#00C851"
                    with st.expander(f"Ticket #{t[0]} - {t[5]} (Status: {t[4].upper()})", expanded=False):
                        st.markdown(f"**Issue Details:** {t[2]}")
                        if t[3]: render_image(t[3], caption="Your Attachment", width=300)
                        st.markdown(f"**Current Status:** <span style='color:{status_color}; font-weight:bold;'>{t[4].upper()}</span>", unsafe_allow_html=True)
            else: st.info("No issues reported.")

        elif choice == "Profile":
            u = get_user_details(st.session_state['user'])
            st.markdown("<h1>👤 My Profile</h1>", unsafe_allow_html=True)
            st.markdown(f"""
            <div style="background: rgba(128,128,128,0.1); padding: 30px; border-radius: 15px; border: 1px solid rgba(255,255,255,0.1);">
                <h2 style="background: -webkit-linear-gradient(45deg, #4facfe, #00f2fe); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">{u[1]}</h2>
                <hr style="border-color: rgba(255,255,255,0.2);">
                <p><b>Roll Number:</b> {u[0]}</p>
                <p><b>Branch & Year:</b> {u[3]} - {u[4]}</p>
                <p><b>Registered Email:</b> {u[7]}</p>
            </div>
            """, unsafe_allow_html=True)

    elif st.session_state['role'] == 'middleman':
        if choice == "Sell Item":
            st.markdown("<h1>🛒 Post Item to Marketplace</h1>", unsafe_allow_html=True)
            with st.form("mm_sell"):
                name = st.text_input("Item Name")
                cat = st.selectbox("Category", ["Books", "Electronics", "Stationery", "Other"])
                price = st.number_input("Price (₹)", min_value=1, step=1)
                desc = st.text_area("Description (Mention original seller details if needed)")
                img = st.file_uploader("Upload Image", type=['jpg', 'png'])
                if st.form_submit_button("Post to Marketplace 🚀"):
                    if name and img:
                        path = save_uploaded_file(img, "images")
                        add_product(st.session_state['user'], name, cat, price, desc, path, 'Sell', 'approved')
                        st.success("✅ Item is now Live on Marketplace!")
                    else: st.error("Name & Image required.")

        elif choice == "Inbox":
            st.markdown("<h1>💬 Inbox & Order Confirmation</h1>", unsafe_allow_html=True)
            partners = get_all_chat_partners(st.session_state['user'])
            c1, c2 = st.columns([2,1])
            with c1:
                if not partners: st.info("No chats yet.")
                else:
                    active_chat = st.selectbox("Chatting with:", partners)
                    st.divider()
                    msgs = get_messages(st.session_state['user'], active_chat)
                    for m in msgs:
                        align = "right" if m[0] == st.session_state['user'] else "left"
                        bg_color = 'linear-gradient(120deg, #e0c3fc 0%, #8ec5fc 100%)' if align=='right' else '#f1f0f0'
                        st.markdown(f"<div style='text-align: {align}; padding: 12px 18px; border-radius: 20px; background: {bg_color}; color: #333; margin: 8px 0; display: inline-block; max-width: 80%; box-shadow: 0 4px 6px rgba(0,0,0,0.05);'><b>{m[0]}</b><br>{m[2]}</div>", unsafe_allow_html=True)
                    with st.form("mm_send_msg", clear_on_submit=True):
                        new_msg = st.text_input("Type a reply...")
                        if st.form_submit_button("Send Reply"):
                            if new_msg: send_message(st.session_state['user'], active_chat, new_msg); st.rerun()
            with c2:
                st.write("### Confirm a Sale")
                active_prods = get_data("SELECT id, product_name FROM productstable WHERE seller_name=%s AND status='approved'", (st.session_state['user'],))
                if active_prods:
                    prod_dict = {f"{p[1]} (ID:{p[0]})": p[0] for p in active_prods}
                    sel_prod = st.selectbox("Select Item Sold", list(prod_dict.keys()))
                    if st.button("Mark as Sold ✅", type="primary"):
                        mark_product_sold(prod_dict[sel_prod])
                        send_message(st.session_state['user'], active_chat, f"✅ ORDER CONFIRMED! I have marked '{sel_prod}' as sold to you.")
                        st.success("Item marked as Sold!"); st.rerun()
                else: st.warning("You have no active items on the marketplace.")

        elif choice == "Help":
            st.markdown("<h1>🆘 Help & Support</h1>", unsafe_allow_html=True)
            with st.form("mm_report_issue", clear_on_submit=True):
                issue_text = st.text_area("Describe your issue...")
                screenshot = st.file_uploader("Attach Screenshot (Optional)", type=['png', 'jpg', 'jpeg'])
                if st.form_submit_button("Submit Issue"):
                    if issue_text:
                        img_path = save_uploaded_file(screenshot, "help_screenshots") if screenshot else None
                        create_help_ticket(st.session_state['user'], issue_text, img_path)
                        st.success("Ticket Created! Admin will review it.")
                        time.sleep(1); st.rerun()
                    else: st.error("Please enter issue details.")
            st.divider()
            st.write("### Your Reported Issues")
            my_tickets = get_my_tickets(st.session_state['user'])
            if my_tickets:
                for t in my_tickets:
                    status_color = "#ff4444" if t[4] == "pending" else "#00C851"
                    with st.expander(f"Ticket #{t[0]} - {t[5]} (Status: {t[4].upper()})", expanded=False):
                        st.markdown(f"**Issue:** {t[2]}")
                        if t[3]: render_image(t[3], caption="Your Attachment", width=300)
                        st.markdown(f"**Status:** <span style='color:{status_color}; font-weight:bold;'>{t[4].upper()}</span>", unsafe_allow_html=True)
            else: st.info("No issues reported.")

        elif choice == "Profile":
            u = get_user_details(st.session_state['user'])
            st.markdown("<h1>👤 Middle Man Profile</h1>", unsafe_allow_html=True)
            st.markdown(f"""
            <div style="background: rgba(128,128,128,0.1); padding: 30px; border-radius: 15px; border: 1px solid rgba(255,255,255,0.1);">
                <h2 style="background: -webkit-linear-gradient(45deg, #4facfe, #00f2fe); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">{u[1]}</h2>
                <hr style="border-color: rgba(255,255,255,0.2);">
                <p><b>Username:</b> {u[0]}</p>
                <p><b>Official Email:</b> {u[7]}</p>
            </div>
            """, unsafe_allow_html=True)

    elif st.session_state['role'] == 'admin':
        if choice == "Dashboard":
            st.markdown("<h1>⚙️ Admin Control Panel</h1>", unsafe_allow_html=True)
            c1, c2, c3 = st.columns(3)
            c1.metric("Pending Approvals", len(get_data("SELECT * FROM userstable WHERE status='pending'")))
            c2.metric("Active Products", len(get_data("SELECT * FROM productstable WHERE status='approved'")))
            c3.metric("Pending Tickets", len(get_pending_tickets()))
            
        elif choice == "Users":
            st.markdown("<h1>👥 Manage Users</h1>", unsafe_allow_html=True)
            st.write("### Pending Approvals")
            pending = get_data("SELECT * FROM userstable WHERE status='pending'")
            if pending:
                for u in pending:
                    with st.expander(f"Pending Request: {u[1]} ({u[0]})", expanded=True):
                        c1, c2 = st.columns(2)
                        with c1: render_image(u[5], width=250)
                        with c2:
                            st.write(f"**Branch:** {u[3]} | **Year:** {u[4]}")
                            st.write(f"**Email:** {u[7]}")
                            if st.button("Approve User ✅", key=f"app_{u[0]}", type="primary"):
                                run_query("UPDATE userstable SET status='approved' WHERE username=%s", (u[0],)); st.rerun()
                            if st.button("Reject User ❌", key=f"rej_{u[0]}"):
                                run_query("DELETE FROM userstable WHERE username=%s", (u[0],)); st.rerun()
            else: st.info("No pending user requests.")

            st.divider()
            st.write("### All Active Students")
            active_users = get_data("SELECT * FROM userstable WHERE status='approved'")
            if active_users:
                for u in active_users:
                    with st.expander(f"User Profile: {u[1]} ({u[0]})"):
                        st.write(f"**Email:** {u[7]}")
                        st.write(f"**Course:** {u[3]} - {u[4]}")
                        if st.button(f"Ban User (Delete) ⚠️", key=f"ban_{u[0]}"):
                            run_query("DELETE FROM userstable WHERE username=%s", (u[0],))
                            st.warning(f"User {u[0]} has been banned (deleted)."); st.rerun()
            else: st.info("No active students found.")

        elif choice == "Products":
            st.markdown("<h1>📦 Manage Products</h1>", unsafe_allow_html=True)
            prods = get_data("SELECT * FROM productstable") 
            if prods:
                for p in prods:
                    c1, c2, c3, c4 = st.columns([3,2,2,1])
                    c1.write(f"**{p[2]}** (₹{p[4]})")
                    c2.write(f"Seller: {p[1]}")
                    c3.write(f"Status: `{p[8]}`")
                    if c4.button("Delete 🗑️", key=f"delp_{p[0]}"):
                        run_query("DELETE FROM productstable WHERE id=%s", (p[0],)); st.rerun()
            else: st.info("No products found in database.")

        elif choice == "Middlemen":
            st.markdown("<h1>🤝 Manage Middle Men</h1>", unsafe_allow_html=True)
            with st.form("add_mm"):
                new_mm_email = st.text_input("Add New Middle Man Email").strip()
                if st.form_submit_button("Authorize Email ✅"):
                    if new_mm_email:
                        add_middleman_email(new_mm_email)
                        st.success(f"{new_mm_email} is now authorized to Sign Up!"); st.rerun()
            st.divider()
            st.write("### Active Middle Men")
            mm_list = get_all_middlemen()
            if mm_list:
                for m in mm_list:
                    c1, c2, c3 = st.columns([2,2,1])
                    c1.write(f"**{m[1]}** (@{m[0]})")
                    c2.write(f"{m[7]}")
                    if c3.button("Revoke Access 🚫", key=f"rem_mm_{m[0]}"):
                        run_query("DELETE FROM userstable WHERE username=%s", (m[0],))
                        run_query("DELETE FROM middleman_emails WHERE email=%s", (m[7],)); st.rerun()
            else: st.info("No active middlemen.")

        elif choice == "Issues":
            st.markdown("<h1>🆘 Pending Help Tickets</h1>", unsafe_allow_html=True)
            tickets = get_pending_tickets()
            if tickets:
                for t in tickets:
                    with st.expander(f"Ticket #{t[0]} from {t[1]} ({t[5]})", expanded=True):
                        st.info(f"**Issue Description:** {t[2]}")
                        if t[3]: render_image(t[3], caption="Attached Screenshot", width=400)
                            
                        reply_key = f"rep_{t[0]}"
                        reply_text = st.text_input("Reply to User (Optional)", key=reply_key)
                        c1, c2 = st.columns(2)
                        if c1.button("Send Reply 📤", key=f"btn_rep_{t[0]}"):
                            if reply_text:
                                send_message('admin', t[1], f"RE: Ticket #{t[0]} - {reply_text}")
                                st.success("Reply sent to user's inbox!")
                        
                        if c2.button("Mark as Resolved ✅", key=f"res_{t[0]}", type="primary"):
                            resolve_ticket(t[0])
                            st.success("Ticket Resolved!"); time.sleep(1); st.rerun()
            else: st.success("No pending issues! Everything is looking good. ✨")
