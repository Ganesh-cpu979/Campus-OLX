import streamlit as st
import sqlite3
import hashlib
import os
import time
import re
import uuid
import random
import string
import smtplib
import ssl
from email.message import EmailMessage
from datetime import datetime
from streamlit_option_menu import option_menu

# --- CONFIGURATION (User must fill this) ---
SENDER_EMAIL = "ganeshjanapuri@gmail.com"  
SENDER_PASSWORD = "bofd bzua sgau kzyv"  

# ----------------------------------------------------
# 1. DATABASE SETUP
# ----------------------------------------------------
if not os.path.exists("images"):
    os.makedirs("images")
if not os.path.exists("id_cards"):
    os.makedirs("id_cards")
if not os.path.exists("help_screenshots"):
    os.makedirs("help_screenshots")

DB_NAME = 'campus_olx.db'

def make_hashes(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def check_hashes(password, hashed_text):
    if make_hashes(password) == hashed_text:
        return hashed_text
    return False

def run_query(query, params=()):
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute(query, params)
        conn.commit()
        return c

def get_data(query, params=()):
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute(query, params)
        data = c.fetchall()
        return data

def get_single_data(query, params=()):
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute(query, params)
        data = c.fetchone()
        return data

# --- Auto Setup Database ---
def init_db():
    run_query('CREATE TABLE IF NOT EXISTS userstable(username TEXT PRIMARY KEY, fullname TEXT, password TEXT, course TEXT, year TEXT, id_card_path TEXT, status TEXT, email TEXT)')
    run_query('CREATE TABLE IF NOT EXISTS productstable(id INTEGER PRIMARY KEY AUTOINCREMENT, seller_name TEXT, product_name TEXT, product_cat TEXT, product_price TEXT, product_desc TEXT, product_img TEXT, type TEXT, status TEXT)')
    run_query('CREATE TABLE IF NOT EXISTS reviewstable(seller_name TEXT, buyer_name TEXT, rating INTEGER, comment TEXT)')
    run_query('CREATE TABLE IF NOT EXISTS messages(sender TEXT, receiver TEXT, message TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)')
    run_query('CREATE TABLE IF NOT EXISTS help_requests(id INTEGER PRIMARY KEY, username TEXT, issue TEXT, image_path TEXT, status TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)')
    run_query('CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, username TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)')
    run_query('CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY AUTOINCREMENT, product_id INTEGER, buyer TEXT, seller TEXT, product_name TEXT, price TEXT, payment_method TEXT, status TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)')

    try: run_query('ALTER TABLE userstable ADD COLUMN email TEXT')
    except: pass
    try: run_query('ALTER TABLE orders ADD COLUMN payment_proof TEXT')
    except: pass
    try: run_query('ALTER TABLE orders ADD COLUMN remark TEXT')
    except: pass
    
    try:
        run_query('INSERT INTO userstable(username, fullname, password, status) VALUES (?,?,?,?)', 
                  ('admin', 'Administrator', make_hashes('admin123'), 'admin'))
    except: pass

# --- Helper Functions ---
def login_user(username, password):
    return get_data('SELECT * FROM userstable WHERE username =? AND password = ?', (username, password))

def get_user_details(username):
    return get_single_data('SELECT * FROM userstable WHERE username=?', (username,))

def add_userdata(username, fullname, password, course, year, id_card_path, email):
    run_query('INSERT INTO userstable(username,fullname,password,course,year,id_card_path,status,email) VALUES (?,?,?,?,?,?,?,?)', 
              (username, fullname, password, course, year, id_card_path, 'pending', email))

def add_product(seller_name, name, cat, price, desc, img, p_type):
    run_query('INSERT INTO productstable(seller_name, product_name, product_cat, product_price, product_desc, product_img, type, status) VALUES (?,?,?,?,?,?,?,?)', 
              (seller_name, name, cat, price, desc, img, p_type, 'pending'))

def view_products(status): return get_data('SELECT * FROM productstable WHERE status=?', (status,))
def update_product_status(pid, stat): run_query('UPDATE productstable SET status=? WHERE id=?', (stat, pid))
def view_users_by_status(stat): return get_data('SELECT * FROM userstable WHERE status=?', (stat,))
def update_user_status(user, stat): run_query('UPDATE userstable SET status=? WHERE username=?', (stat, user))
def add_review(s, b, r, c): run_query('INSERT INTO reviewstable(seller_name, buyer_name, rating, comment) VALUES (?,?,?,?)', (s, b, r, c))
def delete_user(user): run_query('DELETE FROM userstable WHERE username=?', (user,))
def delete_product(pid): run_query('DELETE FROM productstable WHERE id=?', (pid,))
def view_all_users(): return get_data('SELECT * FROM userstable')
def view_all_products(): return get_data('SELECT * FROM productstable')
def add_help_request(user, issue, img_path): run_query('INSERT INTO help_requests(username, issue, image_path, status) VALUES (?,?,?,?)', (user, issue, img_path, 'pending'))
def view_help_requests(status): return get_data('SELECT * FROM help_requests WHERE status=? ORDER BY timestamp DESC', (status,))
def resolve_help_request(rid): run_query('UPDATE help_requests SET status=? WHERE id=?', ('resolved', rid))
def add_order(pid, buyer, seller, pname, price, method, proof=None):
    run_query('INSERT INTO orders(product_id, buyer, seller, product_name, price, payment_method, status, payment_proof) VALUES (?,?,?,?,?,?,?,?)', 
              (pid, buyer, seller, pname, price, method, 'Ordered', proof))
def view_all_orders(): return get_data('SELECT * FROM orders ORDER BY timestamp DESC')
def view_orders_by_status(status): return get_data('SELECT * FROM orders WHERE status=? ORDER BY timestamp DESC', (status,))
def update_order_status(oid, status): run_query('UPDATE orders SET status=? WHERE id=?', (status, oid))
def cancel_order(oid, pid, remark):
    run_query('UPDATE orders SET status=?, remark=? WHERE id=?', ('Cancelled', remark, oid))
    run_query("UPDATE productstable SET status='approved' WHERE id=?", (pid,))
def mark_product_sold(pid): run_query("UPDATE productstable SET status='Sold' WHERE id=?", (pid,))
def get_pending_orders_count(): return len(get_data("SELECT * FROM orders WHERE status='Ordered'"))

# --- SESSION MANAGEMENT ---
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

def send_otp_email(receiver_email, otp):
    if "your_email" in SENDER_EMAIL or "your_app_password" in SENDER_PASSWORD:
        return False, "SIMULATION" 
        
    msg = EmailMessage()
    msg.set_content(f"Subject: Campus OLX - Email Verification\n\nYour OTP for signup is: {otp}\n\nDo not share this with anyone.")
    msg['Subject'] = "Campus OLX - Email Verification OTP"
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

def get_avg_rating(s):
    d = get_data('SELECT rating FROM reviewstable WHERE seller_name=?', (s,))
    return round(sum([x[0] for x in d])/len(d), 1) if d else 0
def save_uploaded_file(f, folder):
    with open(os.path.join(folder, f.name), "wb") as file: file.write(f.getbuffer())
    return os.path.join(folder, f.name)

# --- CHAT FUNCTIONS ---
def send_message(sender, receiver, msg):
    run_query('INSERT INTO messages(sender, receiver, message) VALUES (?,?,?)', (sender, receiver, msg))

def get_messages(user1, user2):
    return get_data('''SELECT * FROM messages 
                       WHERE (sender=? AND receiver=?) OR (sender=? AND receiver=?) 
                       ORDER BY timestamp ASC''', (user1, user2, user2, user1))

def get_all_chat_partners(user):
    sent = get_data("SELECT DISTINCT receiver FROM messages WHERE sender=?", (user,))
    received = get_data("SELECT DISTINCT sender FROM messages WHERE receiver=?", (user,))
    partners = set([x[0] for x in sent] + [x[0] for x in received])
    return list(partners)

def start_chat(seller):
    st.session_state['chat_target'] = seller
    st.session_state['nav_menu'] = "Inbox 💬"

# ----------------------------------------------------
# 2. UI LOGIC
# ----------------------------------------------------
st.set_page_config(page_title="Campus OLX", page_icon="🎓", layout="wide")
init_db()

st.markdown("""
<style>
    .stApp { background-color: #f5f7fa; }
    div[data-testid="stContainer"] { background-color:white; padding:15px; border-radius:10px; box-shadow:0 4px 6px rgba(0,0,0,0.1); }
    .stButton>button { width: 100%; border-radius: 20px; }
    h1, h2, h3 { color: #2c3e50; }
</style>
""", unsafe_allow_html=True)

if 'user' not in st.session_state: st.session_state['user'] = None
if 'role' not in st.session_state: st.session_state['role'] = None
if 'chat_target' not in st.session_state: st.session_state['chat_target'] = None

# For multi-step signup
if 'signup_step' not in st.session_state: st.session_state.signup_step = 1
if 'signup_data' not in st.session_state: st.session_state.signup_data = {}

# --- AUTO LOGIN CHECK ---
if not st.session_state['user']:
    token = st.query_params.get('token')
    if token:
        username = validate_session(token)
        if username:
            st.session_state['user'] = username
            u_data = get_user_details(username)
            if u_data:
                st.session_state['role'] = 'admin' if u_data[6] == 'admin' else 'student'
        else:
            st.query_params.clear()

# --- SIDEBAR ---
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3135/3135715.png", width=100)
    st.title("Campus OLX")
    st.markdown("---")
    
    if st.session_state['user']:
        st.success(f"ID: {st.session_state['user']}")
        if st.session_state['role'] == 'admin':
            menu = ["Dashboard", "Users", "Products", "Pending Orders", "Completed Orders", "Cancelled Orders", "Issues", "Settings"]
            icons = ['speedometer2', 'people', 'box-seam', 'cart-check', 'check-circle', 'x-circle', 'exclamation-circle', 'gear']
            choice = option_menu("Menu", menu, icons=icons, default_index=0) 
        else:
            menu = ["Marketplace", "Sell Item", "Inbox", "Profile"] 
            icons = ['shop', 'plus-circle', 'chat-dots', 'person']
            choice = option_menu("Menu", menu, icons=icons, default_index=0, key='nav_menu')
            
            if 'last_choice' not in st.session_state: st.session_state['last_choice'] = choice
            if st.session_state['last_choice'] != choice:
                st.session_state['extra_page'] = None
                st.session_state['last_choice'] = choice
        
        st.markdown("---")
        if st.session_state['role'] == 'student':
            c1, c2 = st.columns(2)
            if c1.button("💡 How to Use", use_container_width=True):
                st.session_state['extra_page'] = "How to Use"
                st.rerun()
            if c2.button("⚠️ Issues", use_container_width=True):
                st.session_state['extra_page'] = "Issues"
                st.rerun()

        if st.button("Logout 🚪", use_container_width=True):
            token = st.query_params.get('token')
            if token: delete_session(token)
            st.query_params.clear()
            st.session_state['user'] = None; st.session_state['role'] = None; st.rerun()
    else:
        choice = option_menu("Welcome", ["Login", "Sign Up"], icons=['box-arrow-in-right', 'person-plus'], default_index=0)

# ================= LOGIN =================
if choice == "Login":
    st.subheader("🔑 Login to your Account")
    
    with st.form("login_form"):
        username = st.text_input("Username", placeholder="Enter your roll number")
        password = st.text_input("Password", type='password', placeholder="Enter your password")
        submitted = st.form_submit_button("Login", use_container_width=True)
        
        if submitted:
            hashed_pswd = make_hashes(password)
            result = login_user(username, hashed_pswd)
            if result:
                user_data = result[0]
                if user_data[6] in ['admin', 'approved']:
                    st.session_state['user'] = username
                    st.session_state['role'] = 'admin' if user_data[6] == 'admin' else 'student'
                    token = create_session(username)
                    st.query_params['token'] = token
                    st.success(f"Welcome {user_data[1]}") 
                    time.sleep(0.5)
                    st.rerun()
                else: st.warning(f"Account Status: {user_data[6]}")
            else: st.error("❌ Invalid Credentials")
    
    st.info("Don't have an account? Go to the Sign Up page in the sidebar.")

# ================= SIGN UP (NEW MULTI-STEP LOGIC) =================
elif choice == "Sign Up":
    st.markdown("<h2 style='text-align:center;'>📝 Create Account</h2>", unsafe_allow_html=True)
    dept_map = {"CSE": "CS", "ECE": "EC", "EEE": "EE", "Civil": "CE"}
    
    # --- STEP 1: Upload & Details ---
    if st.session_state.signup_step == 1:
        st.info("Step 1: Identity & Details")
        c1, c2 = st.columns(2)
        
        with c1:
            full_name = st.text_input("Full Name", max_chars=10, help="Max 10 characters")
            password = st.text_input("Password", type='password', help="Min 8 characters")
            year = st.selectbox("Year", ["1st Year", "2nd Year", "Final Year"])
            email = st.text_input("Email Address")
            id_front = st.file_uploader("ID Card Front Side", type=['jpg', 'png'])

        with c2:
            username = st.text_input("Roll Number")
            course = st.selectbox("Branch", ["CSE", "ECE", "EEE", "Civil"])
            id_back = st.file_uploader("ID Card Back Side", type=['jpg', 'png'])

        if st.button("Next ➡️", use_container_width=True):
            errors = []
            if not full_name: errors.append("Enter Name")
            if not password or len(password) < 8: errors.append("Password min 8 chars")
            if not username: errors.append("Enter Roll No")
            elif dept_map[course] not in username.upper(): errors.append(f"Roll No must contain '{dept_map[course]}'")
            if not email or not re.match(r"[^@]+@[^@]+\.[^@]+", email): errors.append("Invalid Email")
            if not id_front or not id_back: errors.append("Upload both sides of ID Card")

            if errors:
                for e in errors: st.error(f"⚠️ {e}")
            else:
                # Save front side to DB (as table only has one image column)
                path = save_uploaded_file(id_front, "id_cards")
                # Can also save back side if needed, but DB schema expects one path
                _ = save_uploaded_file(id_back, "id_cards") 
                
                st.session_state.signup_data = {
                    "username": username, "fullname": full_name, "password": make_hashes(password), 
                    "course": course, "year": year, "email": email, "id_card_path": path
                }
                st.session_state.signup_step = 2
                st.rerun()

    # --- STEP 2: Verification ---
    elif st.session_state.signup_step == 2:
        st.info("Step 2: Identity Verification")
        st.write("🔍 **Please check if your ID Card photo is clear:**")
        st.image(st.session_state.signup_data["id_card_path"], width=300)
        
        confirm_clear = st.radio("Is the text on ID card readable?", ["Yes, it's clear", "No, let me re-upload"])
        
        if confirm_clear == "No, let me re-upload":
            if st.button("⬅️ Back to Upload"):
                st.session_state.signup_step = 1
                st.rerun()
        else:
            st.divider()
            c_otp1, c_otp2 = st.columns([2, 1])
            with c_otp1:
                st.write(f"OTP will be sent to: **{st.session_state.signup_data['email']}**")
                if st.button("Send/Verify Email OTP"):
                    otp = generate_otp()
                    st.session_state.signup_otp = otp
                    with st.spinner("Sending OTP..."):
                        success, message = send_otp_email(st.session_state.signup_data['email'], otp)
                    if success: st.success(message)
                    elif message == "SIMULATION":
                        st.warning("⚠️ Email not configured. Using **Simulation Mode**.")
                        st.info(f"🔑 Your OTP is: **{otp}**")
                    else:
                        st.error(message)
                        st.info(f"DEMO MODE: OTP is {otp}") 
            
            with c_otp2:
                if 'signup_otp' in st.session_state:
                    otp_input = st.text_input("Enter OTP")
                    if st.button("Confirm OTP"):
                        if otp_input == st.session_state.signup_otp:
                            st.session_state.signup_step = 3
                            st.rerun()
                        else: st.error("❌ Invalid OTP")

    # --- STEP 3: Terms & Create ---
    elif st.session_state.signup_step == 3:
        st.info("Step 3: Terms & Conditions")
        with st.expander("📜 Read Terms & Conditions", expanded=True):
            st.markdown("""
            1. **Campus Use Only**: This platform is strictly for students and faculty of our campus.
            2. **Legal Items Only**: Selling illegal, prohibited, or harmful items is forbidden.
            3. **Respectful Conduct**: Treat all users with respect.
            4. **Honest Listing**: Describe items accurately.
            """)
        agree_terms = st.checkbox("I agree to the Terms and Conditions")
        
        if st.button("Create Account 🚀", type="primary", use_container_width=True):
            if agree_terms:
                d = st.session_state.signup_data
                try:
                    add_userdata(d['username'], d['fullname'], d['password'], d['course'], d['year'], d['id_card_path'], d['email'])
                    st.balloons()
                    st.success("✅ Account created! Waiting for Admin Approval.")
                    st.session_state.signup_step = 1
                    st.session_state.signup_data = {}
                    time.sleep(2)
                    st.rerun()
                except Exception as e: st.error(f"⚠️ Error: {e}")
            else:
                st.error("⚠️ You must agree to the Terms & Conditions")

# ================= STUDENT EXTRA PAGES =================
elif st.session_state['role'] == 'student' and st.session_state.get('extra_page'):
    if st.session_state['extra_page'] == "How to Use":
        st.title("💡 How to Use Campus OLX")
        st.write("---")
        st.markdown("""
        ### Step-by-Step Guide:
        1. **Signup & Approval**: Register with your roll number and verify your email. Wait for the admin to approve your account.
        2. **Browse Marketplace**: Once logged in, visit the **Marketplace** to see items listed by other students.
        3. **Buy Items**: Click 'Buy Now' on any item. Choose your payment method (Cash or Online via Admin QR). Attach proof for online payments.
        4. **Sell Items**: Go to **Sell Item**, fill in details, upload an image, and list it. Admin will approve it before it goes live.
        5. **Chat with Admin**: Use the **Inbox** to communicate with the administrator regarding orders or queries.
        6. **Check Profile**: Monitor your seller ratings and account details in the **Profile** section.
        7. **Report Issues**: Use the **Issues** button at the bottom of the sidebar to report any problems to the admin.
        """)
        if st.button("Back to Menu"):
            st.session_state['extra_page'] = None
            st.rerun()

    elif st.session_state['extra_page'] == "Issues":
        st.subheader("⚠️ Help & Support (Report an Issue)")
        st.write("Facing an issue? Describe it below and we will get back to you.")
        with st.form("help_form_extra"):
            issue = st.text_area("Describe your issue")
            screenshot = st.file_uploader("Attach Screenshot (Optional)", type=['png', 'jpg', 'jpeg'])
            
            if st.form_submit_button("Send to Admin"):
                if issue:
                    path = None
                    if screenshot:
                        path = save_uploaded_file(screenshot, "help_screenshots")
                    
                    add_help_request(st.session_state['user'], issue, path)
                    send_message(st.session_state['user'], 'admin', f"HELP REQUEST: {issue} (See Issues Tab)")
                    st.success("Ticket Created! Admin will review it.")
                else:
                    st.error("Please enter a message.")
        if st.button("Back to Menu"):
            st.session_state['extra_page'] = None
            st.rerun()

# ================= ADMIN =================
elif st.session_state['role'] == 'admin':
    if choice == "Dashboard":
        st.title("Admin Dashboard")
        c1, c2, c3 = st.columns(3)
        c1.metric("Pending Users", len(view_users_by_status('pending')))
        c2.metric("Pending Products", len(view_products('pending')))
        c3.metric("Pending Orders", get_pending_orders_count())
    elif choice == "Users":
        st.subheader("Manage Users")
        
        pending_users = view_users_by_status('pending')
        if pending_users:
            st.write(f"### Pending Requests ({len(pending_users)})")
            for u in pending_users:
                with st.expander(f"Pending: {u[1]} ({u[0]})", expanded=True):
                    c1, c2 = st.columns([1, 2])
                    with c1:
                        try: st.image(u[5], caption="ID Card", width=250)
                        except: st.error("ID Card Image Not Found")
                    with c2:
                        st.write(f"**Name:** {u[1]}")
                        st.write(f"**Roll No:** {u[0]}")
                        st.write(f"**Branch:** {u[3]}")
                        st.write(f"**Year:** {u[4]}")
                        
                        b1, b2 = st.columns(2)
                        if b1.button("Approve", key=f"app_{u[0]}"): update_user_status(u[0], 'approved'); st.rerun()
                        if b2.button("Reject", key=f"rej_{u[0]}"): update_user_status(u[0], 'rejected'); st.rerun()
        else:
            st.info("No pending user requests.")
            
        st.divider()
        
        st.write("### All Users")
        all_users = view_all_users()
        if all_users:
            for u in all_users:
                if u[6] == 'admin': continue 
                with st.container():
                    c1, c2, c3, c4 = st.columns([2, 2, 2, 1])
                    c1.write(f"**{u[1]}**")
                    c2.write(f"{u[0]}")
                    c3.write(f"Status: `{u[6]}`")
                    if c4.button("Remove", key=f"del_u_{u[0]}"):
                        delete_user(u[0])
                        st.rerun()
                    st.divider()

    elif choice == "Products":
        st.subheader("Manage Products")
        
        pending_products = view_products('pending')
        if pending_products:
            st.write(f"### Pending Approvals ({len(pending_products)})")
            for p in pending_products:
                with st.expander(f"{p[2]} - ₹{p[4]}", expanded=True):
                    c1, c2 = st.columns([1, 2])
                    with c1:
                        try: st.image(p[6], width=200)
                        except: st.write("No Image")
                    with c2:
                        st.write(f"**Seller:** {p[1]}")
                        st.write(f"**Category:** {p[3]}")
                        st.write(f"**Description:** {p[5]}")
                        
                        b1, b2 = st.columns(2)
                        if b1.button("Approve", key=f"app_p_{p[0]}"): update_product_status(p[0], 'approved'); st.rerun()
                        if b2.button("Reject", key=f"rej_p_{p[0]}"): update_product_status(p[0], 'rejected'); st.rerun()
        else:
            st.info("No pending products.")
            
        st.divider()
        
        st.write("### All Products")
        all_prods = view_all_products()
        if all_prods:
            for p in all_prods:
                with st.container():
                    c1, c2, c3, c4 = st.columns([3, 2, 2, 1])
                    c1.write(f"**{p[2]}**")
                    c2.write(f"Seller: {p[1]}")
                    c3.write(f"Status: `{p[8]}`")
                    if c4.button("Remove", key=f"del_p_{p[0]}"):
                        delete_product(p[0])
                        st.rerun()
                    st.divider()

    elif choice == "Issues":
        st.subheader("Manage Help Requests")
        issues = view_help_requests('pending')
        if issues:
            for i in issues:
                with st.expander(f"Issue from {i[1]} ({i[5][:16]})", expanded=True):
                    st.error(f"Issue: {i[2]}")
                    if i[3]:
                        try: st.image(i[3], caption="Screenshot", width=300)
                        except: st.warning("Attachment missing")
                    
                    if st.button("Mark Resolved", key=f"res_{i[0]}"):
                        resolve_help_request(i[0])
                        st.success("Issue Resolved!")
                        time.sleep(0.5)
                        st.rerun()
        else:
            st.info("No pending issues.")
            
    elif choice == "Pending Orders":
        st.subheader("Manage Pending Orders")
        orders = view_orders_by_status('Ordered')
        if orders:
            for o in orders:
                status = o[7]; method = o[6]
                
                with st.expander(f"Order #{o[0]}: {o[4]}", expanded=True):
                    c1, c2, c3 = st.columns(3)
                    c1.write(f"**Buyer:** {o[2]}")
                    c2.write(f"**Seller:** {o[3]}")
                    c3.write(f"**Method:** {o[6]}")
                    st.write(f"**Price:** ₹{o[5]}")
                    
                    if status == 'Cancelled':
                        st.error(f"Cancelled: {o[-1]}") 
                    
                    if method == "Online (Pay to Admin)":
                        try:
                            proof_path = o[9] if len(o) > 9 else None
                            if proof_path:
                                abs_path = os.path.abspath(proof_path)
                                if os.path.exists(abs_path):
                                    st.image(abs_path, caption="Payment Proof", width=300)
                                else:
                                    st.warning(f"⚠️ File not found at: {proof_path}")
                            else:
                                st.warning("⚠️ No Payment Proof Found in DB")
                        except Exception as e: 
                            st.error(f"Error loading proof: {e}")

                    b1, b2, b3 = st.columns(3)
                    
                    if b1.button("Mark Completed", key=f"ord_c_{o[0]}"):
                        update_order_status(o[0], 'Completed')
                        mark_product_sold(o[1]) 
                        st.success("Order Completed & Item Sold")
                        st.rerun()
                    
                    with b2.expander("Cancel Order"):
                            rem = st.text_input("Reason", key=f"rem_{o[0]}")
                            if st.button("Confirm Cancel", key=f"can_{o[0]}"):
                                cancel_order(o[0], o[1], rem)
                                st.warning("Order Cancelled & Item Restored")
                                st.rerun()

                    with st.expander(f"Chat with Buyer ({o[2]})"):
                        st.write(f"Chatting with Buyer of Order #{o[0]}")
                        msgs = get_messages('admin', o[2])
                        if msgs:
                            for m in msgs:
                                st.text(f"{m[0]}: {m[2]}")
                        
                        msg_b = st.text_input("Message to Buyer", key=f"msg_b_{o[0]}")
                        if st.button("Send", key=f"snd_b_{o[0]}"):
                            send_message('admin', o[2], msg_b)
                            st.rerun()

                    with st.expander(f"Chat with Seller ({o[3]})"):
                        st.write(f"Chatting with Seller of Order #{o[0]}")
                        msgs = get_messages('admin', o[3])
                        if msgs:
                            for m in msgs:
                                st.text(f"{m[0]}: {m[2]}")
                        
                        msg_s = st.text_input("Message to Seller", key=f"msg_s_{o[0]}")
                        if st.button("Send", key=f"snd_s_{o[0]}"):
                            send_message('admin', o[3], msg_s)
                            st.rerun()
        else:
            st.info("No pending orders.")

    elif choice == "Completed Orders":
        st.subheader("Completed Orders History")
        orders = view_orders_by_status('Completed')
        if orders:
            for o in orders:
                with st.expander(f"Order #{o[0]}: {o[4]} (Completed)", expanded=False):
                    c1, c2, c3 = st.columns(3)
                    c1.write(f"**Buyer:** {o[2]}")
                    c2.write(f"**Seller:** {o[3]}")
                    c3.write(f"**Method:** {o[6]}")
                    st.write(f"**Price:** ₹{o[5]}")
                    st.success("✅ Order Completed")

                    with st.expander("View Chat History"):
                        tab1, tab2 = st.tabs(["Buyer Chat", "Seller Chat"])
                        with tab1:
                            msgs = get_messages('admin', o[2])
                            for m in msgs: st.text(f"{m[0]}: {m[2]}")
                        with tab2:
                            msgs = get_messages('admin', o[3])
                            for m in msgs: st.text(f"{m[0]}: {m[2]}")
        else:
            st.info("No completed orders.")

    elif choice == "Cancelled Orders":
        st.subheader("Cancelled Orders History")
        orders = view_orders_by_status('Cancelled')
        if orders:
            for o in orders:
                with st.expander(f"Order #{o[0]}: {o[4]} (Cancelled)", expanded=False):
                    c1, c2, c3 = st.columns(3)
                    c1.write(f"**Buyer:** {o[2]}")
                    c2.write(f"**Seller:** {o[3]}")
                    c3.write(f"**Method:** {o[6]}")
                    st.write(f"**Price:** ₹{o[5]}")
                    
                    remark = "No remark"
                    if len(o) > 10: remark = o[10] 
                    elif len(o) > 0: remark = o[-1] 
                    
                    st.error(f"❌ Cancelled. Reason: {remark}")

                    with st.expander("View Chat History"):
                        tab1, tab2 = st.tabs(["Buyer Chat", "Seller Chat"])
                        with tab1:
                            msgs = get_messages('admin', o[2])
                            for m in msgs: st.text(f"{m[0]}: {m[2]}")
                        with tab2:
                            msgs = get_messages('admin', o[3])
                            for m in msgs: st.text(f"{m[0]}: {m[2]}")
        else:
            st.info("No cancelled orders.")

    elif choice == "Settings":
        st.subheader("Admin Settings")
        st.write("Upload your QR Code for 'Online' payments.")
        qr_file = st.file_uploader("Admin QR Code", type=['png', 'jpg', 'jpeg'])
        if qr_file:
            with open("admin_qr.png", "wb") as f:
                f.write(qr_file.getbuffer())
            st.success("✅ Admin QR Code Updated!")
        
        if os.path.exists("admin_qr.png"):
            st.image("admin_qr.png", caption="Current Admin QR", width=200)

# ================= STUDENT =================
elif st.session_state['role'] == 'student':
    
    # 1. MARKETPLACE
    if choice == "Marketplace":
        st.title("🛒 Marketplace")
        search = st.text_input("🔍 Search...")
        all_prods = view_products('approved')
        filtered = [p for p in all_prods if search.lower() in p[2].lower()]
        
        if not filtered: st.info("No items found.")
        cols = st.columns(3)
        for i, p in enumerate(filtered):
            with cols[i%3]:
                with st.container():
                    try: st.image(p[6], use_container_width=True)
                    except: st.write("📷 No Image")
                    st.markdown(f"**{p[2]}**")
                    st.markdown(f"**₹{p[4]}**" if p[7] == 'Sell' else "<span style='color:green'>🎁 FREE</span>", unsafe_allow_html=True)
                    st.caption(f"Seller: {p[1]}")
                    
                    if p[1] != st.session_state['user']: 
                        if st.button(f"Buy Now 🛒", key=f"buy_{p[0]}"):
                            st.session_state['buying_product'] = p
                            st.rerun()
                    else:
                        st.button("Your Item", disabled=True, key=f"dis_{p[0]}")
                    st.divider()

        if 'buying_product' in st.session_state and st.session_state['buying_product']:
            p = st.session_state['buying_product']
            st.write(f"### Buying: {p[2]}")
            st.write(f"Price: ₹{p[4]}")
            method = st.radio("Payment Method", ["Cash", "Online (Pay to Admin)"])
            
            proof_path = None
            if method == "Online (Pay to Admin)":
                if os.path.exists("admin_qr.png"):
                    st.image("admin_qr.png", caption="Scan to Pay Admin", width=250)
                    proof_file = st.file_uploader("Upload Payment Screenshot (Required)", type=['jpg', 'png', 'jpeg'])
                    
                    if proof_file:
                        if not os.path.exists("payment_proofs"): os.makedirs("payment_proofs")
                        proof_path = os.path.join("payment_proofs", f"proof_{p[0]}_{st.session_state['user']}.png")
                        with open(proof_path, "wb") as f: f.write(proof_file.getbuffer())
                    else:
                        st.warning("⚠️ You must attach a screenshot to proceed.")
                else:
                    st.warning("⚠️ Admin QR not set. Please use Cash or contact Admin.")
            
            if method == "Online (Pay to Admin)" and not proof_path:
                st.button("Confirm Order (Upload Proof First)", disabled=True)
            else:
                if st.button("Confirm Order"):
                    add_order(p[0], st.session_state['user'], p[1], p[2], p[4], method, proof_path)
                    mark_product_sold(p[0])
                    
                    st.balloons()
                    st.success("✅ Order Placed! Item marked as Sold.")
                    del st.session_state['buying_product']
                    time.sleep(2)
                    st.rerun()
            
            if st.button("Cancel"):
                del st.session_state['buying_product']
                st.rerun()

    # 3. OTHER PAGES
    elif choice == "Inbox":
        st.title("📩 Inbox (Chat with Admin)")
        
        active_chat = 'admin'
        
        msgs = get_messages(st.session_state['user'], active_chat)
        if msgs:
            for m in msgs:
                align = "right" if m[0] == st.session_state['user'] else "left"
                bg_color = '#dcf8c6' if align=='right' else '#f1f0f0'
                st.markdown(f"<div style='text-align: {align}; padding: 10px; border-radius: 10px; background-color: {bg_color}; margin: 5px; display: inline-block; max-width: 80%;'><b>{m[0]}</b>: {m[2]}</div>", unsafe_allow_html=True)
                st.write("") 
        else:
            st.info("No messages with Admin yet.")

        st.write("---")
        with st.form("chat_admin", clear_on_submit=True):
            msg = st.text_input("Type a message to Admin...")
            if st.form_submit_button("Send"):
                if msg:
                    send_message(st.session_state['user'], active_chat, msg)
                    st.rerun()

    elif choice == "Sell Item":
        st.subheader("Sell Your Item")
        with st.form("sell"):
            name = st.text_input("Item Name")
            cat = st.selectbox("Category", ["Books", "Electronics", "Stationery", "Other"])
            type_c = st.radio("Type", ["Sell", "Donate"])
            price = st.number_input("Price (₹70 - ₹150)", min_value=70, max_value=150, step=1) if type_c == "Sell" else "0"
            desc = st.text_area("Description")
            img = st.file_uploader("Image", type=['jpg', 'png'])
            
            if st.form_submit_button("List Item"):
                if name and img:
                    path = save_uploaded_file(img, "images")
                    add_product(st.session_state['user'], name, cat, price, desc, path, type_c)
                    st.success("Listed for Approval!")
                else: st.error("Name & Image required.")

    elif choice == "Profile":
        u = get_user_details(st.session_state['user'])
        st.markdown(f"## 👤 {u[1]}")
        st.write(f"Roll No: **{u[0]}** | Branch: {u[3]}")
        st.info(f"Seller Rating: ⭐ {get_avg_rating(u[0])}/5")
        try: st.image(u[5], width=200)
        except: pass
