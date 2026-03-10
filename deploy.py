import streamlit as st
import sqlite3
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
SENDER_EMAIL = "your mail"  
SENDER_PASSWORD = "two step mail verification password"  

# ----------------------------------------------------
# 1. DATABASE SETUP (SQLITE 3)
# ----------------------------------------------------
DB_NAME = 'campus_olx.db'

def get_db_connection():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

def make_hashes(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def run_query(query, params=()):
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute(query, params)
        conn.commit()

def get_data(query, params=()):
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute(query, params)
        return c.fetchall()

def get_single_data(query, params=()):
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute(query, params)
        return c.fetchone()

def init_db():
    run_query('CREATE TABLE IF NOT EXISTS userstable(username TEXT PRIMARY KEY, fullname TEXT, password TEXT, course TEXT, year TEXT, id_card_path TEXT, status TEXT, email TEXT, is_subscribed INTEGER DEFAULT 0)')
    run_query('CREATE TABLE IF NOT EXISTS productstable(id INTEGER PRIMARY KEY AUTOINCREMENT, seller_name TEXT, product_name TEXT, product_cat TEXT, product_price TEXT, product_desc TEXT, product_img TEXT, type TEXT, status TEXT)')
    run_query('CREATE TABLE IF NOT EXISTS messages(sender TEXT, receiver TEXT, message TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)')
    run_query('CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, username TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)')
    run_query('CREATE TABLE IF NOT EXISTS delivery_agent_emails(email TEXT PRIMARY KEY, registered INTEGER DEFAULT 0)')
    run_query('CREATE TABLE IF NOT EXISTS help_tickets(id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, issue TEXT, image_path TEXT, status TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)')
    run_query('CREATE TABLE IF NOT EXISTS deals(id INTEGER PRIMARY KEY AUTOINCREMENT, product_id INTEGER, seller TEXT, buyer TEXT, delivery_mode TEXT, status TEXT)')
    
    # Migrations 
    try: run_query('ALTER TABLE userstable ADD COLUMN is_subscribed INTEGER DEFAULT 0')
    except: pass
    try: run_query('ALTER TABLE help_tickets ADD COLUMN image_path TEXT')
    except: pass
    try: run_query('ALTER TABLE deals ADD COLUMN cancel_reason TEXT')
    except: pass

    try:
        run_query('INSERT INTO userstable(username, fullname, password, status, is_subscribed) VALUES (?,?,?,?,?)', 
                  ('admin', 'Administrator', make_hashes('admin123'), 'admin', 1))
    except: pass

# --- DB Helper Functions ---
def is_username_taken(username):
    if not username: return False
    res = get_single_data("SELECT username FROM userstable WHERE LOWER(username)=LOWER(?)", (username.strip(),))
    return res is not None

def is_email_taken(email):
    if not email: return False
    res = get_single_data("SELECT email FROM userstable WHERE LOWER(email)=LOWER(?)", (email.strip(),))
    return res is not None

def login_user(username, password):
    return get_data('SELECT * FROM userstable WHERE username=? AND password=?', (username.strip(), password))

def get_user_details(username):
    return get_single_data('SELECT * FROM userstable WHERE username=?', (username,))

def update_password(username, new_password):
    run_query('UPDATE userstable SET password=? WHERE username=?', (make_hashes(new_password), username))

def add_userdata(username, fullname, password, course, year, id_card_path, email, status='pending'):
    run_query('INSERT INTO userstable(username,fullname,password,course,year,id_card_path,status,email,is_subscribed) VALUES (?,?,?,?,?,?,?,?,0)', 
              (username.strip(), fullname.strip(), password, course, year, id_card_path, status, email.strip()))

def add_product(seller_name, name, cat, price, desc, img_paths, p_type, status='pending'):
    run_query('INSERT INTO productstable(seller_name, product_name, product_cat, product_price, product_desc, product_img, type, status) VALUES (?,?,?,?,?,?,?,?)', 
              (seller_name, name, cat, price, desc, img_paths, p_type, status))

# --- Deals & Cancellation Logic ---
def propose_deal(product_id, seller, buyer, delivery_mode):
    run_query("INSERT INTO deals(product_id, seller, buyer, delivery_mode, status) VALUES (?,?,?,?, 'Proposed')", (product_id, seller, buyer, delivery_mode))

def confirm_deal(deal_id, product_id):
    run_query("UPDATE deals SET status='Confirmed' WHERE id=?", (deal_id,))
    run_query("UPDATE productstable SET status='Sold' WHERE id=?", (product_id,))

def cancel_deal(deal_id, product_id, reason):
    run_query("UPDATE deals SET status='Cancelled', cancel_reason=? WHERE id=?", (reason, deal_id))
    run_query("UPDATE productstable SET status='approved' WHERE id=?", (product_id,))

def get_all_delivery_agents():
    return get_data("SELECT * FROM userstable WHERE status='delivery_agent'")

def add_delivery_agent_email(email):
    try: run_query("INSERT INTO delivery_agent_emails(email) VALUES (?)", (email.strip(),))
    except: pass

def check_delivery_agent_email(email):
    return get_single_data("SELECT registered FROM delivery_agent_emails WHERE email=?", (email.strip(),))

def register_delivery_agent_email(email):
    run_query("UPDATE delivery_agent_emails SET registered=1 WHERE email=?", (email.strip(),))

def subscribe_user(username):
    run_query("UPDATE userstable SET is_subscribed=1 WHERE username=?", (username,))

def create_help_ticket(username, issue, image_path=None):
    run_query("INSERT INTO help_tickets(username, issue, image_path, status) VALUES (?, ?, ?, 'pending')", (username, issue, image_path))

def get_pending_tickets():
    return get_data("SELECT * FROM help_tickets WHERE status='pending' ORDER BY timestamp DESC")

def resolve_ticket(ticket_id):
    run_query("UPDATE help_tickets SET status='resolved' WHERE id=?", (ticket_id,))

def get_my_tickets(username):
    return get_data("SELECT * FROM help_tickets WHERE username=? ORDER BY timestamp DESC", (username,))

def create_session(username):
    token = str(uuid.uuid4())
    run_query('INSERT INTO sessions(token, username) VALUES (?,?)', (token, username))
    return token

def validate_session(token):
    data = get_single_data('SELECT username FROM sessions WHERE token=?', (token,))
    return data[0] if data else None

def delete_session(token):
    run_query('DELETE FROM sessions WHERE token=?', (token,))

def generate_otp():
    return ''.join(random.choices(string.digits, k=6))

# --- CHAT PROFANITY FILTER ---
BANNED_WORDS = ['love', 'ishq', 'ishqbaazi', 'abuse', 'stupid', 'idiot', 'pagal', 'gadha', 'kamina', 'sale']
def filter_chat(msg):
    clean_msg = msg
    for word in BANNED_WORDS:
        clean_msg = re.sub(r'(?i)\b' + word + r'\b', '***', clean_msg)
    return clean_msg

# --- IMAGE HANDLING (BASE64) ---
def save_uploaded_file(f):
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
    clean_msg = filter_chat(msg)
    run_query('INSERT INTO messages(sender, receiver, message) VALUES (?,?,?)', (sender, receiver, clean_msg))

def get_messages(user1, user2):
    return get_data('''SELECT * FROM messages 
                       WHERE (sender=? AND receiver=?) OR (sender=? AND receiver=?) 
                       ORDER BY timestamp ASC''', (user1, user2, user2, user1))

def get_all_chat_partners(user):
    sent = get_data("SELECT DISTINCT receiver FROM messages WHERE sender=?", (user,))
    received = get_data("SELECT DISTINCT sender FROM messages WHERE receiver=?", (user,))
    return list(set([x[0] for x in sent] + [x[0] for x in received]))

# ----------------------------------------------------
# 2. APP INITIALIZATION & ADVANCED UI STYLES
# ----------------------------------------------------
st.set_page_config(page_title="Campus OLX", page_icon="🎓", layout="wide")
init_db()

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

# Session States
if 'user' not in st.session_state: st.session_state['user'] = None
if 'role' not in st.session_state: st.session_state['role'] = None
if 'signup_step' not in st.session_state: st.session_state.signup_step = 1
if 'show_payment_wall' not in st.session_state: st.session_state.show_payment_wall = False

if not st.session_state['user']:
    token = st.query_params.get('token')
    if token:
        username = validate_session(token)
        if username:
            st.session_state['user'] = username
            u_data = get_user_details(username)
            if u_data:
                role = 'admin' if u_data[6] == 'admin' else ('delivery_agent' if u_data[6] == 'delivery_agent' else 'student')
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
            menu = ["Dashboard", "Users", "Products", "Delivery Agents", "Issues"]
            icons = ['speedometer2', 'people', 'box-seam', 'person-badge', 'check-square']
        elif role == 'delivery_agent':
            menu = ["Inbox", "Help", "Profile"]
            icons = ['chat-dots', 'question-circle', 'person']
        else: 
            menu = ["Marketplace", "Sell Item", "Inbox", "Help", "Profile"] 
            icons = ['shop', 'plus-circle', 'chat-dots', 'question-circle', 'person']
            
        choice = option_menu("Menu", menu, icons=icons, default_index=0)
        st.markdown("---")
        if st.button("Logout 🚪", use_container_width=True):
            token = st.query_params.get('token')
            if token: delete_session(token)
            st.query_params.clear()
            st.session_state['user'] = None; st.session_state['role'] = None
            st.session_state.show_payment_wall = False
            st.rerun()
    else:
        choice = option_menu("Welcome", 
                             ["Login", "Student Sign Up", "Delivery Agent Auth", "How to Use", "About Us"], 
                             icons=['box-arrow-in-right', 'person-plus', 'truck', 'book', 'info-circle'], 
                             default_index=0)

if not st.session_state['user']:
    if choice == "Login":
        st.markdown("<h1>🔑 Welcome Back</h1>", unsafe_allow_html=True)
        with st.form("login_form"):
            username = st.text_input("Roll Number / Admin ID").strip()
            password = st.text_input("Password", type='password')
            if st.form_submit_button("Login Securely"):
                result = login_user(username, make_hashes(password))
                if result:
                    u_data = result[0]
                    if u_data[6] in ['admin', 'approved', 'delivery_agent']:
                        st.session_state['user'] = username
                        st.session_state['role'] = 'admin' if u_data[6] == 'admin' else ('delivery_agent' if u_data[6] == 'delivery_agent' else 'student')
                        st.query_params['token'] = create_session(username)
                        st.rerun()
                    else: st.warning(f"Account Status: {u_data[6]}")
                else: st.error("❌ Invalid Credentials")

    elif choice == "Student Sign Up":
        st.markdown("<h1 style='text-align:center;'>📝 Student Registration</h1>", unsafe_allow_html=True)
        with st.form("signup_form"):
            full_name = st.text_input("Full Name")
            username = st.text_input("Roll Number")
            email = st.text_input("Official Email")
            password = st.text_input("Password", type='password')
            id_front = st.file_uploader("Upload ID Card Photo", type=['jpg', 'png'])
            if st.form_submit_button("Create Account"):
                if is_username_taken(username): st.error("Roll Number already registered!")
                elif id_front and username and email and password:
                    path = save_uploaded_file(id_front)
                    add_userdata(username, full_name, make_hashes(password), "N/A", "N/A", path, email, 'pending')
                    st.success("✅ Account created! Waiting for Admin Approval.")
                else: st.error("Fill all fields")

    elif choice == "Delivery Agent Auth":
        st.markdown("<h1>🚚 Delivery Agent Login/Signup</h1>", unsafe_allow_html=True)
        log_type = st.radio("Select", ["Login", "Register"])
        if log_type == "Login":
            username = st.text_input("Agent Username/ID").strip()
            password = st.text_input("Password", type='password')
            if st.button("Login"):
                res = login_user(username, make_hashes(password))
                if res and res[0][6] == 'delivery_agent':
                    st.session_state['user'] = username; st.session_state['role'] = 'delivery_agent'
                    st.query_params['token'] = create_session(username)
                    st.rerun()
                else: st.error("❌ Invalid Credentials")
        else:
            email = st.text_input("Enter Authorized Email").strip()
            if st.button("Check Eligibility"):
                status = check_delivery_agent_email(email)
                if status is None: st.error("❌ Email not authorized by Admin.")
                elif status[0] == 1: st.error("❌ Already registered.")
                else:
                    st.success("✅ Authorized! Please setup profile.")
                    st.session_state.da_verified = True; st.session_state.da_email = email
            
            if st.session_state.get('da_verified'):
                with st.form("da_setup"):
                    da_name = st.text_input("Full Name").strip()
                    da_user = st.text_input("Choose Username").strip()
                    da_pwd = st.text_input("Setup Password", type='password')
                    if st.form_submit_button("Register Agent"):
                        if is_username_taken(da_user): st.error("Username taken!")
                        else:
                            add_userdata(da_user, da_name, make_hashes(da_pwd), "N/A", "N/A", "N/A", st.session_state.da_email, 'delivery_agent')
                            register_delivery_agent_email(st.session_state.da_email)
                            st.success("Registered! Please Login."); st.session_state.da_verified = False

    elif choice == "How to Use":
        st.markdown("<h1 style='text-align:center;'>📖 How to Use Campus OLX</h1>", unsafe_allow_html=True)
        st.markdown("<div style='background: rgba(30, 30, 30, 0.4); backdrop-filter: blur(12px); border-radius: 15px; padding: 30px; border: 1px solid rgba(255,255,255,0.1); margin-top: 20px;'><h3 style='color: #4facfe;'>🎓 For Students</h3><ol style='color: #e2e8f0; line-height: 1.8; font-size: 16px;'><li><b>Browse:</b> View marketplace items freely.</li><li><b>Subscription:</b> Pay ₹1 fee only when you try to Contact a Seller or List an item.</li><li><b>Buy & Sell:</b> Chat securely.</li><li><b>Deals:</b> Both seller and buyer must confirm an order. Orders can be cancelled with a reason, restoring the item to the marketplace.</li></ol></div>", unsafe_allow_html=True)

    elif choice == "About Us":
        st.markdown("<h1 style='text-align:center;'>ℹ️ About Us</h1>", unsafe_allow_html=True)
        st.markdown("<div style='background: rgba(30, 30, 30, 0.4); backdrop-filter: blur(12px); border-radius: 15px; padding: 30px; border: 1px solid rgba(255,255,255,0.1); margin-top: 20px;'><h3 style='color: #4facfe;'>🌟 Our Vision</h3><p style='color: #e2e8f0; font-size: 16px; line-height: 1.6;'>A seamless, secure localized marketplace.</p><h3 style='color: #4facfe;'>👨‍💻 Developed By</h3><ul style='color: #e2e8f0; font-size: 16px; line-height: 1.8;'><li><b>Ganesh</b> <span style='color:#00f2fe;'>(Team Lead)</span></li><li><b>Sairam</b>, <b>Navyasri</b>, <b>Akshitha</b>, <b>Mrigank</b>, <b>Manish</b></li></ul></div>", unsafe_allow_html=True)

else:
    u_details = get_user_details(st.session_state['user'])
    is_subscribed = u_details[8] if u_details else 0

    if st.session_state['role'] == 'student':
        # --- THE SMART PAYMENT WALL INTERCEPTOR ---
        if st.session_state.get('show_payment_wall', False) and not is_subscribed:
            st.markdown("<h1>⭐ Premium Access Required</h1>", unsafe_allow_html=True)
            st.warning("You need an active subscription to Contact Sellers or Post new items.")
            with st.container():
                st.write("### 🚀 Campus Pass - ₹1")
                st.write("✔️ Contact any Seller\n✔️ Sell unlimited items\n✔️ Secure chat & Delivery Agents")
                
                c1, c2 = st.columns(2)
                if c1.button("Pay ₹1 & Subscribe Now", type="primary", use_container_width=True):
                    subscribe_user(st.session_state['user'])
                    st.session_state.show_payment_wall = False
                    st.balloons()
                    st.success("✅ Payment Successful! Subscription Activated. You can now proceed.")
                    time.sleep(2)
                    st.rerun()
                if c2.button("⬅️ Cancel & Go Back", use_container_width=True):
                    st.session_state.show_payment_wall = False
                    st.rerun()
        else:
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
                        first_image = p[6].split('|')[0] if p[6] else None
                        render_image(first_image, use_container_width=True)
                        st.markdown(f"<h3>{p[2]}</h3>", unsafe_allow_html=True)
                        st.markdown(f"<h2 style='color:#00E676; margin:0; -webkit-text-fill-color: #00E676;'>₹{p[4]}</h2>", unsafe_allow_html=True)
                        st.caption(f"Category: {p[3]} | Seller: {p[1]}")
                        
                        if p[1] != st.session_state['user']:
                            # Subcription check is done when button is clicked!
                            if st.button(f"Contact Seller", key=f"buy_{p[0]}", use_container_width=True):
                                if not is_subscribed:
                                    st.session_state.show_payment_wall = True
                                    st.rerun()
                                else:
                                    send_message(st.session_state['user'], p[1], f"Hi, I want to buy your item: **{p[2]}** (₹{p[4]}). Is it available?")
                                    st.success("Message sent! Check your Inbox.")
                        st.markdown("</div><br>", unsafe_allow_html=True)

            elif choice == "Sell Item":
                st.markdown("<h1>📦 Sell Your Item</h1>", unsafe_allow_html=True)
                st.info("Upload multiple photos. Max price allowed is ₹500. Admin will review before posting.")
                with st.form("sell_form"):
                    name = st.text_input("Item Name")
                    cat = st.selectbox("Category", ["Books", "Electronics", "Stationery", "Other"])
                    price = st.number_input("Price (Max ₹500)", min_value=1, max_value=500, step=1)
                    desc = st.text_area("Item Details")
                    imgs = st.file_uploader("Upload Photos (Multiple allowed)", type=['jpg', 'png'], accept_multiple_files=True)
                    
                    if st.form_submit_button("Submit for Approval 🚀"):
                        # Check subscription on submit
                        if not is_subscribed:
                            st.session_state.show_payment_wall = True
                            st.rerun()
                        elif name and imgs and price <= 500:
                            paths = [save_uploaded_file(img) for img in imgs]
                            path_str = "|".join(paths) 
                            add_product(st.session_state['user'], name, cat, price, desc, path_str, 'Sell', 'pending')
                            st.success("✅ Item submitted to Admin for approval!")
                        else: st.error("Please fill all fields, ensure price is <= ₹500, and upload at least 1 image.")

            elif choice == "Inbox":
                st.markdown("<h1>💬 Inbox & Deals</h1>", unsafe_allow_html=True)
                partners = get_all_chat_partners(st.session_state['user'])
                if 'admin' in partners: partners.remove('admin')
                
                if not partners: st.info("No messages yet.")
                else:
                    c1, c2 = st.columns([2,1])
                    with c1:
                        active_chat = st.selectbox("Chatting with:", partners)
                        st.divider()
                        msgs = get_messages(st.session_state['user'], active_chat)
                        for m in msgs:
                            align = "right" if m[0] == st.session_state['user'] else "left"
                            bg_color = 'linear-gradient(135deg, #a8edea 0%, #fed6e3 100%)' if align=='right' else '#f1f0f0'
                            st.markdown(f"<div style='text-align: {align}; padding: 12px 18px; border-radius: 20px; background: {bg_color}; color: #333; margin: 8px 0; display: inline-block; max-width: 80%; box-shadow: 0 4px 6px rgba(0,0,0,0.05);'><b>{m[0]}</b><br>{m[2]}</div>", unsafe_allow_html=True)
                        with st.form("send_msg", clear_on_submit=True):
                            new_msg = st.text_input("Type your message here... (Filtered securely)")
                            if st.form_submit_button("Send Message 🚀"):
                                if new_msg:
                                    send_message(st.session_state['user'], active_chat, new_msg); st.rerun()
                    
                    with c2:
                        st.write("### 🛍️ Deal Actions")
                        current_deal = get_single_data(
                            "SELECT * FROM deals WHERE ((seller=? AND buyer=?) OR (seller=? AND buyer=?)) AND status IN ('Proposed', 'Confirmed') ORDER BY id DESC LIMIT 1", 
                            (st.session_state['user'], active_chat, active_chat, st.session_state['user'])
                        )

                        if current_deal:
                            deal_id, p_id, d_seller, d_buyer, d_mode, d_status = current_deal[0], current_deal[1], current_deal[2], current_deal[3], current_deal[4], current_deal[5]
                            
                            if d_status == 'Proposed':
                                if st.session_state['user'] == d_seller:
                                    st.info("⌛ You have proposed a deal. Waiting for buyer to confirm.")
                                    if st.button("Cancel Proposal"):
                                        run_query("UPDATE deals SET status='Cancelled' WHERE id=?", (deal_id,))
                                        send_message(st.session_state['user'], active_chat, "🚫 I have withdrawn my deal proposal.")
                                        st.rerun()
                                else:
                                    st.warning(f"🔔 {active_chat} has proposed a deal!")
                                    if st.button("Accept & Confirm Order ✅", type="primary", use_container_width=True):
                                        confirm_deal(deal_id, p_id)
                                        st.success("Deal Confirmed! Item removed from marketplace.")
                                        if d_mode == 'Delivery Agent':
                                            agents = get_all_delivery_agents()
                                            if agents:
                                                send_message(st.session_state['user'], agents[0][0], f"New Delivery Request: Collect item from {active_chat} and deliver to {st.session_state['user']}.")
                                        send_message(st.session_state['user'], active_chat, "✅ I have accepted and confirmed the deal. The item has been marked as Sold!")
                                        time.sleep(2); st.rerun()
                                    if st.button("Reject Proposal ❌", use_container_width=True):
                                        run_query("UPDATE deals SET status='Cancelled' WHERE id=?", (deal_id,))
                                        send_message(st.session_state['user'], active_chat, "❌ I have rejected the deal proposal.")
                                        st.rerun()

                            elif d_status == 'Confirmed':
                                st.success("✅ Order is Confirmed for this chat.")
                                with st.expander("❌ Cancel this Order"):
                                    with st.form("cancel_order_form"):
                                        cancel_reason = st.text_input("Reason for cancellation (Required)")
                                        if st.form_submit_button("Submit Cancellation"):
                                            if cancel_reason:
                                                cancel_deal(deal_id, p_id, cancel_reason)
                                                send_message(st.session_state['user'], active_chat, f"❌ ORDER CANCELLED.\nReason: {cancel_reason}")
                                                st.success("Order cancelled. Item is back live on the marketplace!")
                                                time.sleep(2); st.rerun()
                                            else:
                                                st.error("Please provide a reason to cancel the order.")
                        else:
                            active_prods = get_data("SELECT id, product_name FROM productstable WHERE seller_name=? AND status='approved'", (st.session_state['user'],))
                            if active_prods:
                                with st.expander("🤝 Propose a Deal (As Seller)"):
                                    with st.form("propose_deal_form"):
                                        prod_dict = {f"{p[1]} (ID:{p[0]})": p[0] for p in active_prods}
                                        sel_prod = st.selectbox("Select Item to Sell", list(prod_dict.keys()))
                                        del_mode = st.radio("Delivery Type", ["Self Delivery", "Delivery Agent"])
                                        if st.form_submit_button("Send Proposal"):
                                            propose_deal(prod_dict[sel_prod], st.session_state['user'], active_chat, del_mode)
                                            send_message(st.session_state['user'], active_chat, f"I have proposed a deal for '{sel_prod.split(' (')[0]}' via {del_mode}. Please click 'Accept' in the Deal Actions to confirm.")
                                            st.success("Proposal sent!"); time.sleep(1); st.rerun()

                        st.divider()
                        st.write("### ⚙️ User Actions")
                        if st.button("🚫 Block User", use_container_width=True): st.error(f"User {active_chat} Blocked!")
                        
                        # --- ADVANCED REPORT SYSTEM ---
                        with st.expander("⚠️ Report User"):
                            with st.form("report_form"):
                                rep_reason = st.text_area("Reason for reporting")
                                rep_img = st.file_uploader("Upload Evidence (Screenshot)", type=['png', 'jpg', 'jpeg'])
                                if st.form_submit_button("Submit Report"):
                                    if rep_reason:
                                        img_path = save_uploaded_file(rep_img) if rep_img else None
                                        create_help_ticket(st.session_state['user'], f"Reported against {active_chat}: {rep_reason}", img_path)
                                        st.success("Report successfully sent to Admin for review.")
                                    else:
                                        st.error("Please enter a reason to report.")

            elif choice == "Help":
                st.markdown("<h1>🆘 Help & Support</h1>", unsafe_allow_html=True)
                with st.form("report_issue", clear_on_submit=True):
                    issue_text = st.text_area("Describe your issue in detail...")
                    screenshot = st.file_uploader("Attach Screenshot (Optional)", type=['png', 'jpg', 'jpeg'])
                    if st.form_submit_button("Submit Issue Ticket"):
                        if issue_text:
                            img_path = save_uploaded_file(screenshot) if screenshot else None
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
                    <p><b>Pass Status:</b> {'Active Premium ⭐' if is_subscribed else 'Inactive ❌'}</p>
                </div>
                """, unsafe_allow_html=True)

    elif st.session_state['role'] == 'delivery_agent':
        if choice == "Inbox":
            st.markdown("<h1>🚚 Delivery Agent Inbox</h1>", unsafe_allow_html=True)
            partners = get_all_chat_partners(st.session_state['user'])
            c1, c2 = st.columns([2,1])
            with c1:
                if not partners: st.info("No delivery requests yet.")
                else:
                    active_chat = st.selectbox("Chatting with:", partners)
                    st.divider()
                    msgs = get_messages(st.session_state['user'], active_chat)
                    for m in msgs:
                        align = "right" if m[0] == st.session_state['user'] else "left"
                        bg_color = 'linear-gradient(120deg, #e0c3fc 0%, #8ec5fc 100%)' if align=='right' else '#f1f0f0'
                        st.markdown(f"<div style='text-align: {align}; padding: 12px 18px; border-radius: 20px; background: {bg_color}; color: #333; margin: 8px 0; display: inline-block; max-width: 80%; box-shadow: 0 4px 6px rgba(0,0,0,0.05);'><b>{m[0]}</b><br>{m[2]}</div>", unsafe_allow_html=True)
                    with st.form("da_send_msg", clear_on_submit=True):
                        new_msg = st.text_input("Type a reply...")
                        if st.form_submit_button("Send Reply"):
                            if new_msg: send_message(st.session_state['user'], active_chat, new_msg); st.rerun()
            with c2:
                st.write("### Actions")
                if st.button("Mark Delivery Complete ✅", type="primary", use_container_width=True):
                    send_message(st.session_state['user'], active_chat, "✅ Item has been successfully delivered!")
                    st.success("Status Updated.")

        elif choice == "Help":
            st.markdown("<h1>🆘 Help & Support</h1>", unsafe_allow_html=True)
            with st.form("da_report_issue", clear_on_submit=True):
                issue_text = st.text_area("Describe your issue...")
                if st.form_submit_button("Submit Issue"):
                    if issue_text:
                        create_help_ticket(st.session_state['user'], issue_text)
                        st.success("Ticket Created!"); time.sleep(1); st.rerun()
                    else: st.error("Please enter issue details.")

        elif choice == "Profile":
            u = get_user_details(st.session_state['user'])
            st.markdown("<h1>👤 Delivery Agent Profile</h1>", unsafe_allow_html=True)
            st.markdown(f"""
            <div style="background: rgba(128,128,128,0.1); padding: 30px; border-radius: 15px; border: 1px solid rgba(255,255,255,0.1);">
                <h2 style="background: -webkit-linear-gradient(45deg, #4facfe, #00f2fe); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">{u[1]}</h2>
                <hr style="border-color: rgba(255,255,255,0.2);">
                <p><b>Agent ID:</b> {u[0]}</p>
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
                                run_query("UPDATE userstable SET status='approved' WHERE username=?", (u[0],)); st.rerun()
                            if st.button("Reject User ❌", key=f"rej_{u[0]}"):
                                run_query("DELETE FROM userstable WHERE username=?", (u[0],)); st.rerun()
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
                            run_query("DELETE FROM userstable WHERE username=?", (u[0],))
                            st.warning(f"User {u[0]} has been banned."); st.rerun()
            else: st.info("No active students found.")

        elif choice == "Products":
            st.markdown("<h1>📦 Manage Products</h1>", unsafe_allow_html=True)
            st.write("### Pending Approvals")
            prods = get_data("SELECT * FROM productstable WHERE status='pending'")
            if prods:
                for p in prods:
                    st.write(f"**{p[2]}** by {p[1]} (₹{p[4]})")
                    first_image = p[6].split('|')[0] if p[6] else None
                    render_image(first_image, width=150)
                    if st.button(f"Approve Item {p[0]}", type="primary"):
                        run_query("UPDATE productstable SET status='approved' WHERE id=?", (p[0],)); st.rerun()
                    st.divider()
            else: st.info("No products waiting for approval.")

        elif choice == "Delivery Agents":
            st.markdown("<h1>🚚 Manage Delivery Agents</h1>", unsafe_allow_html=True)
            with st.form("add_da"):
                new_da_email = st.text_input("Add New Delivery Agent Email").strip()
                if st.form_submit_button("Authorize Email ✅"):
                    if new_da_email:
                        add_delivery_agent_email(new_da_email)
                        st.success(f"{new_da_email} is now authorized to Sign Up!"); st.rerun()
            st.divider()
            st.write("### Active Delivery Agents")
            da_list = get_all_delivery_agents()
            if da_list:
                for m in da_list:
                    c1, c2, c3 = st.columns([2,2,1])
                    c1.write(f"**{m[1]}** (@{m[0]})")
                    c2.write(f"{m[7]}")
                    if c3.button("Revoke Access 🚫", key=f"rem_da_{m[0]}"):
                        run_query("DELETE FROM userstable WHERE username=?", (m[0],))
                        run_query("DELETE FROM delivery_agent_emails WHERE email=?", (m[7],)); st.rerun()
            else: st.info("No active delivery agents.")

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
