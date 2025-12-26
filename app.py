import streamlit as st
import sqlite3
import hashlib
import os
import time

# ----------------------------------------------------
# 1. DATABASE SETUP (SAFE MODE)
# ----------------------------------------------------
if not os.path.exists("images"):
    os.makedirs("images")
if not os.path.exists("id_cards"):
    os.makedirs("id_cards")

DB_NAME = 'campus_olx.db'

def make_hashes(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def check_hashes(password, hashed_text):
    if make_hashes(password) == hashed_text:
        return hashed_text
    return False

# --- SAFE DATABASE FUNCTIONS ---
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

# Tables Create
def create_tables():
    # User Table
    run_query('''CREATE TABLE IF NOT EXISTS userstable(
                 username TEXT PRIMARY KEY, password TEXT, mobile TEXT, 
                 course TEXT, year TEXT, id_card_path TEXT, status TEXT)''')
    
    # Product Table
    run_query('''CREATE TABLE IF NOT EXISTS productstable(
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 seller_name TEXT, product_name TEXT, product_cat TEXT, 
                 product_price TEXT, product_desc TEXT, product_img TEXT,
                 type TEXT, status TEXT)''')
    
    # NEW: Reviews Table 🌟
    run_query('''CREATE TABLE IF NOT EXISTS reviewstable(
                 seller_name TEXT, buyer_name TEXT, rating INTEGER, comment TEXT)''')
    
    # Create Default Admin
    try:
        run_query('INSERT INTO userstable(username, password, status) VALUES (?,?,?)', 
                  ('admin', make_hashes('admin123'), 'admin'))
    except:
        pass

# --- FUNCTIONS ---
def add_userdata(username, password, mobile, course, year, id_card_path):
    run_query('INSERT INTO userstable(username,password,mobile,course,year,id_card_path,status) VALUES (?,?,?,?,?,?,?)', 
              (username, password, mobile, course, year, id_card_path, 'pending'))

def login_user(username, password):
    return get_data('SELECT * FROM userstable WHERE username =? AND password = ?', (username, password))

def get_user_details(username):
    return get_single_data('SELECT * FROM userstable WHERE username=?', (username,))

def add_product(seller_name, name, cat, price, desc, img, p_type):
    run_query('INSERT INTO productstable(seller_name, product_name, product_cat, product_price, product_desc, product_img, type, status) VALUES (?,?,?,?,?,?,?,?)', 
              (seller_name, name, cat, price, desc, img, p_type, 'pending'))

def view_products(status_filter):
    return get_data('SELECT * FROM productstable WHERE status=?', (status_filter,))

def update_product_status(p_id, new_status):
    run_query('UPDATE productstable SET status=? WHERE id=?', (new_status, p_id))

def view_users_by_status(status):
    return get_data('SELECT * FROM userstable WHERE status=?', (status,))

def update_user_status(username, new_status):
    run_query('UPDATE userstable SET status=? WHERE username=?', (new_status, username))

def save_uploaded_file(uploadedfile, folder):
    with open(os.path.join(folder, uploadedfile.name), "wb") as f:
        f.write(uploadedfile.getbuffer())
    return os.path.join(folder, uploadedfile.name)

# --- REVIEW FUNCTIONS ---
def add_review(seller, buyer, rating, comment):
    run_query('INSERT INTO reviewstable(seller_name, buyer_name, rating, comment) VALUES (?,?,?,?)', 
              (seller, buyer, rating, comment))

def get_avg_rating(seller):
    data = get_data('SELECT rating FROM reviewstable WHERE seller_name=?', (seller,))
    if data:
        total = sum([x[0] for x in data])
        return round(total / len(data), 1)
    return 0  # No ratings yet

# ----------------------------------------------------
# 2. UI LOGIC
# ----------------------------------------------------
st.set_page_config(page_title="Campus OLX Secure", page_icon="🔒", layout="wide")
create_tables()

st.title("🎓 Secured Campus Bazaar")

if 'user' not in st.session_state:
    st.session_state['user'] = None
if 'role' not in st.session_state:
    st.session_state['role'] = None

# --- MENU SYSTEM ---
menu = ["Home/Login", "SignUp (Student)"]
if st.session_state['user']:
    if st.session_state['role'] == 'admin':
        menu = ["Admin Dashboard", "Manage Users", "Manage Products", "Logout"]
    else:
        menu = ["Marketplace (Buy)", "Sell Item", "Rate a Seller", "My Profile", "Logout"]

choice = st.sidebar.selectbox("Menu", menu)

# ================= GUEST / LOGIN =================
if choice == "Home/Login":
    st.subheader("Login Panel")
    username = st.text_input("Username")
    password = st.text_input("Password", type='password')
    
    if st.button("Login"):
        hashed_pswd = make_hashes(password)
        result = login_user(username, hashed_pswd)
        
        if result:
            user_data = result[0]
            status = user_data[6] 
            
            if status == 'admin':
                st.session_state['user'] = username
                st.session_state['role'] = 'admin'
                st.success("Admin Logged In!")
                time.sleep(0.5)
                st.rerun()
            
            elif status == 'approved':
                st.session_state['user'] = username
                st.session_state['role'] = 'student'
                st.success("Welcome Student!")
                time.sleep(0.5)
                st.rerun()
                
            elif status == 'pending':
                st.warning("⚠️ Account Pending Approval.")
            elif status == 'banned':
                st.error("🚫 You are BANNED.")
            elif status == 'rejected':
                st.error("🚫 Account Rejected.")
        else:
            st.error("Invalid Credentials")

# ================= SIGNUP =================
elif choice == "SignUp (Student)":
    st.subheader("Student Registration")
    with st.form("signup_form"):
        c1, c2 = st.columns(2)
        with c1:
            new_user = st.text_input("Username (Roll No)")
            new_pass = st.text_input("Password", type='password')
            new_mobile = st.text_input("Phone Number")
        with c2:
            course = st.text_input("Course")
            year = st.selectbox("Year", ["1st", "2nd", "3rd", "Final"])
            id_card = st.file_uploader("ID Card Photo", type=['jpg', 'png'])
        
        submitted = st.form_submit_button("Submit")
        if submitted:
            if id_card and new_user and new_pass:
                id_path = save_uploaded_file(id_card, "id_cards")
                try:
                    add_userdata(new_user, make_hashes(new_pass), new_mobile, course, year, id_path)
                    st.success("✅ Request Sent!")
                except:
                    st.error("Username taken.")
            else:
                st.error("All fields mandatory!")

# ================= LOGOUT =================
elif choice == "Logout":
    st.session_state['user'] = None
    st.session_state['role'] = None
    st.success("Logged Out")
    time.sleep(0.5)
    st.rerun()

# ================= ADMIN =================
elif st.session_state['role'] == 'admin':
    if choice == "Admin Dashboard":
        st.info("Welcome Admin")
        st.metric("Pending Users", len(view_users_by_status('pending')))
        st.metric("Pending Products", len(view_products('pending')))

    elif choice == "Manage Users":
        st.subheader("User Management")
        pending_users = view_users_by_status('pending')
        if pending_users:
            for u in pending_users:
                with st.expander(f"Request: {u[0]}"):
                    c1, c2 = st.columns([1,2])
                    with c1:
                        try: st.image(u[5], width=150)
                        except: st.write("No Img")
                    with c2:
                        st.write(f"Mobile: {u[2]}")
                        if st.button("Approve", key=f"a_{u[0]}"):
                            update_user_status(u[0], 'approved'); st.rerun()
                        if st.button("Reject", key=f"r_{u[0]}"):
                            update_user_status(u[0], 'rejected'); st.rerun()
        else:
            st.info("No pending users.")
            
        st.markdown("---")
        search_u = st.text_input("Ban/Unban User (Enter Username)")
        if search_u:
            if st.button("Ban User"):
                update_user_status(search_u, 'banned'); st.warning("Banned!"); st.rerun()
            if st.button("Unban User"):
                update_user_status(search_u, 'approved'); st.success("Unbanned!"); st.rerun()

    elif choice == "Manage Products":
        st.subheader("Product Approvals")
        pending_prods = view_products('pending')
        if pending_prods:
            for p in pending_prods:
                with st.expander(f"{p[2]} by {p[1]}"):
                    st.image(p[6], width=100)
                    st.write(f"Price: {p[4]} | Desc: {p[5]}")
                    if st.button("Approve", key=f"pa_{p[0]}"):
                        update_product_status(p[0], 'approved'); st.rerun()
                    if st.button("Reject", key=f"pr_{p[0]}"):
                        update_product_status(p[0], 'rejected'); st.rerun()

# ================= STUDENT =================
elif st.session_state['role'] == 'student':
    
    # 1. PROFILE
    if choice == "My Profile":
        user_info = get_user_details(st.session_state['user'])
        st.subheader(f"Profile: {user_info[0]}")
        try: st.image(user_info[5], width=200, caption="ID Card")
        except: pass
        st.write(f"Course: {user_info[3]} | Mobile: {user_info[2]}")
        
        # Show My Rating
        my_rating = get_avg_rating(st.session_state['user'])
        st.info(f"🌟 Your Seller Rating: {my_rating} / 5.0")

    # 2. SELL ITEM
    elif choice == "Sell Item":
        st.subheader("Sell or Donate")
        type_choice = st.radio("Type", ["Sell", "Donate"])
        
        with st.form("sell"):
            name = st.text_input("Item Name")
            cat = st.selectbox("Category", ["Books", "Electronics", "Stationery", "Others"])
            price = st.text_input("Price") if type_choice == "Sell" else "0"
            desc = st.text_area("Description")
            img = st.file_uploader("Photo", type=['jpg', 'png'])
            
            if st.form_submit_button("Submit"):
                if name and img:
                    path = save_uploaded_file(img, "images")
                    add_product(st.session_state['user'], name, cat, price, desc, path, type_choice)
                    st.success("Submitted for Approval!")
                else: st.error("Name & Image required")

    # 3. RATE SELLER (NEW FEATURE) 🌟
    elif choice == "Rate a Seller":
        st.subheader("⭐ Rate & Review a Seller")
        st.info("Bought something? Share your feedback to help others.")
        
        # List of all users (except self and admin)
        all_users = get_data("SELECT username FROM userstable WHERE status='approved'")
        seller_list = [u[0] for u in all_users if u[0] != st.session_state['user']]
        
        with st.form("rating_form"):
            target_seller = st.selectbox("Select Seller", seller_list)
            stars = st.slider("Rating (1-5)", 1, 5, 5)
            review_text = st.text_area("Comment (e.g. Good product, Honest guy)")
            
            if st.form_submit_button("Submit Review"):
                add_review(target_seller, st.session_state['user'], stars, review_text)
                st.success(f"Rated {target_seller} successfully!")
                st.balloons()

    # 4. MARKETPLACE
    elif choice == "Marketplace (Buy)":
        st.subheader("🛒 Campus Marketplace")
        
        all_products = view_products('approved')
        # Combined Sell/Donate for simple view
        search = st.text_input("🔍 Search...")
        
        if all_products:
            for p in all_products:
                if search.lower() in p[2].lower() or search == "":
                    
                    seller_name = p[1]
                    seller_info = get_user_details(seller_name)
                    phone = seller_info[2] if seller_info else "0000"
                    
                    # FETCH SELLER RATING
                    seller_rating = get_avg_rating(seller_name)
                    star_display = "⭐" * int(seller_rating) if seller_rating > 0 else "New Seller"
                    
                    with st.container():
                        st.write("")
                        c1, c2, c3 = st.columns([1, 2, 1])
                        
                        with c1:
                            try: st.image(p[6], use_container_width=True)
                            except: st.error("No Img")
                        
                        with c2:
                            st.subheader(p[2])
                            st.caption(f"Category: {p[3]}")
                            st.write(f"**{p[5]}**")
                            
                            # SELLER INFO WITH RATING
                            st.write(f"👤 **{seller_name}** | Rating: {seller_rating}/5 {star_display}")
                            
                            price_tag = "FREE (Donation)" if p[7] == "Donate" else f"₹{p[4]}"
                            st.success(f"🏷️ {price_tag}")

                        with c3:
                            st.write("### Buy Now")
                            if p[7] == "Sell":
                                pay = st.radio("Pay via:", ["Cash", "UPI"], key=p[0])
                                if pay == "Cash":
                                    msg = f"Hi {seller_name}, I want to buy {p[2]} via Cash."
                                else:
                                    st.code(f"{phone}@paytm")
                                    msg = f"Hi {seller_name}, paying online for {p[2]}."
                            else:
                                st.info("🎁 Donation")
                                msg = f"Hi {seller_name}, collecting donation {p[2]}."

                            link = f"https://wa.me/91{phone}?text={msg}"
                            st.markdown(f'<a href="{link}" target="_blank"><button style="width:100%; padding:8px; background-color:#25D366; color:white; border:none; border-radius:5px;">Chat on WhatsApp</button></a>', unsafe_allow_html=True)
                        st.markdown("---")