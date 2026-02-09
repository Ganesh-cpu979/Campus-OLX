import streamlit as st
import sqlite3
import hashlib
import os
import time
import re
from datetime import datetime
from streamlit_option_menu import option_menu 

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
    run_query('CREATE TABLE IF NOT EXISTS userstable(username TEXT PRIMARY KEY, fullname TEXT, password TEXT, course TEXT, year TEXT, id_card_path TEXT, status TEXT)')
    run_query('CREATE TABLE IF NOT EXISTS productstable(id INTEGER PRIMARY KEY AUTOINCREMENT, seller_name TEXT, product_name TEXT, product_cat TEXT, product_price TEXT, product_desc TEXT, product_img TEXT, type TEXT, status TEXT)')
    run_query('CREATE TABLE IF NOT EXISTS reviewstable(seller_name TEXT, buyer_name TEXT, rating INTEGER, comment TEXT)')
    run_query('CREATE TABLE IF NOT EXISTS messages(sender TEXT, receiver TEXT, message TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)')
    run_query('CREATE TABLE IF NOT EXISTS help_requests(id INTEGER PRIMARY KEY, username TEXT, issue TEXT, image_path TEXT, status TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)')
    
    try:
        run_query('INSERT INTO userstable(username, fullname, password, status) VALUES (?,?,?,?)', 
                  ('admin', 'Administrator', make_hashes('admin123'), 'admin'))
    except: pass

# --- Helper Functions ---
def login_user(username, password):
    return get_data('SELECT * FROM userstable WHERE username =? AND password = ?', (username, password))

def get_user_details(username):
    return get_single_data('SELECT * FROM userstable WHERE username=?', (username,))

def add_userdata(username, fullname, password, course, year, id_card_path):
    run_query('INSERT INTO userstable(username,fullname,password,course,year,id_card_path,status) VALUES (?,?,?,?,?,?,?)', 
              (username, fullname, password, course, year, id_card_path, 'pending'))

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

# --- SIDEBAR ---
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3135/3135715.png", width=100)
    st.title("Campus OLX")
    st.markdown("---")
    
    if st.session_state['user']:
        st.success(f"ID: {st.session_state['user']}")
        if st.session_state['role'] == 'admin':
            menu = ["Dashboard", "Users", "Products", "Issues", "Logout"]
            icons = ['speedometer2', 'people', 'box-seam', 'exclamation-circle', 'box-arrow-right']
            choice = option_menu("Menu", menu, icons=icons, default_index=0) # Admin menu simple rakha hai
        else:
            menu = ["Marketplace", "Inbox 💬", "Sell Item", "Help", "Profile", "Logout"]
            icons = ['shop', 'chat-dots', 'plus-circle', 'question-circle', 'person', 'box-arrow-right']
            # KEY Added for programmatic control 👇
            choice = option_menu("Menu", menu, icons=icons, default_index=0, key='nav_menu')
    else:
        choice = option_menu("Welcome", ["Login", "Sign Up"], icons=['box-arrow-in-right', 'person-plus'], default_index=0)

# ================= LOGIN =================
if choice == "Login":
    st.markdown("<br>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        with st.container():
            st.markdown("""
            <div style="background-color: white; padding: 30px; border-radius: 15px; box-shadow: 0 4px 15px rgba(0,0,0,0.1); text-align: center;">
                <h2 style="color: #2c3e50; margin-bottom: 5px;">Welcome Back! 👋</h2>
                <p style="color: #7f8c8d; font-size: 14px;">Please login to access your account</p>
            </div>
            """, unsafe_allow_html=True)
            st.markdown("<br>", unsafe_allow_html=True)
            
            with st.form("login_form"):
                username = st.text_input("Roll Number", placeholder="Enter your Roll No.")
                password = st.text_input("Password", type='password', placeholder="Enter Password")
                submitted = st.form_submit_button("Secure Login", use_container_width=True)
                
                if submitted:
                    hashed_pswd = make_hashes(password)
                    result = login_user(username, hashed_pswd)
                    if result:
                        user_data = result[0]
                        if user_data[6] in ['admin', 'approved']:
                            st.session_state['user'] = username
                            st.session_state['role'] = 'admin' if user_data[6] == 'admin' else 'student'
                            st.success(f"Login Successful! Welcome {user_data[1]}") 
                            time.sleep(0.5)
                            st.rerun()
                        else: st.warning(f"Account Status: {user_data[6]}. Please wait for approval.")
                    else: st.error("❌ Invalid Roll Number or Password")

# ================= SIGN UP =================
elif choice == "Sign Up":
    st.markdown("<h2 style='text-align:center;'>📝 Create Account</h2>", unsafe_allow_html=True)
    dept_map = {"CSE": "CS", "ECE": "EC", "EEE": "EE", "Civil": "CE"}
    
    # Initialize error state if not present
    if 'signup_errors' not in st.session_state:
        st.session_state.signup_errors = {}
    
    errors = st.session_state.signup_errors

    with st.form("signup"):
        c1, c2 = st.columns(2)
        
        with c1:
            full_name = st.text_input("Full Name")
            if 'name' in errors: st.error(errors['name'])
            
            password = st.text_input("Password", type='password', help="Min 8 characters")
            if 'password' in errors: st.error(errors['password'])
            
            year = st.selectbox("Year", ["1st Year", "2nd Year", "Final Year"])

        with c2:
            username = st.text_input("Roll Number")
            if 'username' in errors: st.error(errors['username'])
            
            course = st.selectbox("Branch", ["CSE", "ECE", "EEE", "Civil"])
            
            id_card = st.file_uploader("ID Card Photo", type=['jpg', 'png'])
            if 'id_card' in errors: st.error(errors['id_card'])
        
        st.markdown("<br>", unsafe_allow_html=True)
        submitted = st.form_submit_button("Register Now", use_container_width=True)
        
        if submitted:
            new_errors = {}
            
            # Validation Logic
            if not full_name: new_errors['name'] = "⚠️ Enter your Full Name"
            elif not re.match(r"^[a-zA-Z\s]+$", full_name): new_errors['name'] = "⚠️ Only alphabets allowed"
            
            if not password: new_errors['password'] = "⚠️ Enter a Password"
            elif len(password) < 8: new_errors['password'] = "⚠️ Password must be 8+ chars"
            
            if not username: new_errors['username'] = "⚠️ Enter Roll Number"
            else:
                required_code = dept_map[course]
                if required_code not in username.upper():
                    new_errors['username'] = f"⚠️ Roll No. must contain '{required_code}'"
            
            if not id_card: new_errors['id_card'] = "⚠️ Upload ID Card"

            if new_errors:
                st.session_state.signup_errors = new_errors
                st.rerun()
            else:
                st.session_state.signup_errors = {} # Clear errors
                path = save_uploaded_file(id_card, "id_cards")
                try:
                    add_userdata(username, full_name, make_hashes(password), course, year, path)
                    st.balloons()
                    st.success("✅ Account created! Waiting for Admin Approval.")
                except Exception as e: st.error("⚠️ User already exists or Database Error.")

elif choice == "Logout":
    st.session_state['user'] = None; st.session_state['role'] = None; st.rerun()

# ================= ADMIN =================
elif st.session_state['role'] == 'admin':
    if choice == "Dashboard":
        st.title("Admin Dashboard")
        c1, c2 = st.columns(2)
        c1.metric("Pending Users", len(view_users_by_status('pending')))
        c2.metric("Pending Products", len(view_products('pending')))
    elif choice == "Users":
        st.subheader("Manage Users")
        
        # Pending Requests
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
        
        # All Users Management
        st.write("### All Users")
        all_users = view_all_users()
        if all_users:
            for u in all_users:
                if u[6] == 'admin': continue # Skip admin
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
        
        # Pending Products
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
        
        # All Products Management
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
                    
                    # --- FIXED CHAT LOGIC ---
                    if p[1] != st.session_state['user']: 
                        st.button(f"Chat with {p[1]} 💬", key=f"btn_{p[0]}", on_click=start_chat, args=(p[1],))
                    else:
                        st.button("Your Item", disabled=True, key=f"dis_{p[0]}")
                    st.divider()

    # 2. INBOX (CHAT SYSTEM)
    elif choice == "Inbox 💬":
        st.title("💬 Messages")
        partners = get_all_chat_partners(st.session_state['user'])
        
        if st.session_state['chat_target'] and st.session_state['chat_target'] not in partners:
            partners.append(st.session_state['chat_target'])
        
        if not partners:
            st.info("No messages yet.")
        else:
            c1, c2 = st.columns([1, 3])
            with c1:
                st.subheader("Contacts")
                idx = 0
                if st.session_state['chat_target'] in partners:
                    idx = partners.index(st.session_state['chat_target'])
                
                selected_user = st.radio("Select User:", partners, index=idx)
                if st.button("Refresh Chat 🔄"): st.rerun()

            with c2:
                if selected_user:
                    st.subheader(f"Chat with {selected_user}")
                    messages = get_messages(st.session_state['user'], selected_user)
                    chat_container = st.container(height=400)
                    
                    with chat_container:
                        for sender, receiver, msg, ts in messages:
                            if sender == st.session_state['user']:
                                with st.chat_message("user"):
                                    st.write(msg)
                            else:
                                with st.chat_message("assistant"):
                                    st.write(msg)
                                    st.caption(f"{ts[11:16]}")
                    
                    if prompt := st.chat_input("Type a message..."):
                        send_message(st.session_state['user'], selected_user, prompt)
                        st.rerun()

    # 3. OTHER PAGES
    elif choice == "Sell Item":
        st.subheader("Sell Your Item")
        with st.form("sell"):
            name = st.text_input("Item Name")
            cat = st.selectbox("Category", ["Books", "Electronics", "Stationery", "Other"])
            type_c = st.radio("Type", ["Sell", "Donate"])
            price = st.text_input("Price") if type_c == "Sell" else "0"
            desc = st.text_area("Description")
            img = st.file_uploader("Image", type=['jpg', 'png'])
            
            if st.form_submit_button("List Item"):
                if name and img:
                    path = save_uploaded_file(img, "images")
                    add_product(st.session_state['user'], name, cat, price, desc, path, type_c)
                    st.success("Listed for Approval!")
                else: st.error("Name & Image required.")

    elif choice == "Help":
        st.subheader("Help & Support")
        st.write("Facing an issue? Describe it below and we will get back to you.")
        with st.form("help_form"):
            issue = st.text_area("Describe your issue")
            screenshot = st.file_uploader("Attach Screenshot (Optional)", type=['png', 'jpg', 'jpeg'])
            
            if st.form_submit_button("Send to Admin"):
                if issue:
                    path = None
                    if screenshot:
                        path = save_uploaded_file(screenshot, "help_screenshots")
                    
                    add_help_request(st.session_state['user'], issue, path)
                    # Also send a chat message notification
                    send_message(st.session_state['user'], 'admin', f"HELP REQUEST: {issue} (See Issues Tab)")
                    st.success("Ticket Created! Admin will review it.")
                else:
                    st.error("Please enter a message.")

    elif choice == "Profile":
        u = get_user_details(st.session_state['user'])
        st.markdown(f"## 👤 {u[1]}")
        st.write(f"Roll No: **{u[0]}** | Branch: {u[3]}")
        st.info(f"Seller Rating: ⭐ {get_avg_rating(u[0])}/5")
        try: st.image(u[5], width=200)
        except: pass
