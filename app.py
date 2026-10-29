import os
import re
import uuid
from pathlib import Path
from decimal import Decimal, InvalidOperation
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, abort, jsonify
from chatbot import answer_message
from sqlalchemy.exc import IntegrityError
from config import Config
from models import db, User, Product, Category, Cart, CartItem, Order, OrderItem
from recommender import recommend
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_wtf.csrf import CSRFProtect, CSRFError

app = Flask(__name__)
app.config.from_object(Config)

csrf = CSRFProtect(app)

db.init_app(app)

login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.init_app(app)


@login_manager.unauthorized_handler
def unauthorized():
    flash("Pehle login karo.", "error")
    # next sirf GET page ke liye; POST-only route (add-to-cart) par login ke baad 405 aata
    if request.method == "GET":
        return redirect(url_for("login", next=request.full_path.rstrip("?")))
    return redirect(url_for("login"))

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return login_manager.unauthorized()
        if not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated

def safe_recommend(product_ids, limit=4):
    try:
        return recommend(product_ids, limit)
    except Exception as e:
        app.logger.warning("Recommendation error: %s", e)
        return []

UPLOAD_DIR = Path(app.static_folder) / "images"
GENERATED_IMAGE_RE = re.compile(r"^[0-9a-f]{32}\.(jpg|png|webp)$")


def detect_image_ext(stream):
    """File ke asli bytes dekhke type batata hai (naam pe bharosa nahi)."""
    head = stream.read(12)
    stream.seek(0)
    if head.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    return None


def save_product_image(file_storage):
    """Sahi image ho to random naam se save karke naam wapas karta hai, warna None."""
    ext = detect_image_ext(file_storage.stream)
    if not ext:
        return None
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.{ext}"
    file_storage.save(UPLOAD_DIR / filename)
    return filename


def delete_product_image(filename):
    """Sirf wahi files delete karta hai jo humne upload se banayi hon."""
    if not filename or not GENERATED_IMAGE_RE.match(filename):
        return
    try:
        (UPLOAD_DIR / filename).unlink(missing_ok=True)
    except OSError:
        pass


def is_safe_next(url):
    """Sirf apni site ke andar ke redirect allow karo (open redirect se bachao)."""
    return bool(url) and url.startswith("/") and not url.startswith("//") and "\\" not in url


def restock_order(order):
    """Cancel hone par order ka stock wapas add karo."""
    for item in order.items:
        p = db.session.get(Product, item.product_id)
        if p:
            p.stock = (p.stock or 0) + item.quantity


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@app.context_processor
def inject_cart_count():
    count = 0
    if current_user.is_authenticated:
        count = (
            db.session.query(db.func.coalesce(db.func.sum(CartItem.quantity), 0))
            .select_from(CartItem)
            .join(Cart, Cart.id == CartItem.cart_id)
            .filter(Cart.user_id == current_user.id)
            .scalar()
        )
    return {"cart_count": int(count)}


@app.errorhandler(CSRFError)
def handle_csrf_error(e):
    if request.path == "/ask-ai":
        return jsonify({"reply": "Session expire ho gaya, page refresh karo.", "products": []}), 400
    flash("Session expire ho gaya, dobara try karo.", "error")
    return redirect(request.referrer or url_for("home"))

@app.errorhandler(403)
@app.errorhandler(404)
@app.errorhandler(405)
@app.errorhandler(413)         
@app.errorhandler(500)
def handle_http_error(e):
    code = getattr(e, "code", 500)
    messages = {
        403: "Aapko is page ki permission nahi hai.",
        404: "Ye page nahi mila.",
        405: "Ye action is tareeke se allowed nahi hai.",
        413: "File bahut badi hai. 2 MB se choti image upload karo.",    
        500: "Server me kuch gadbad ho gayi. Thodi der baad try karo.",
    }
    if code == 500:
        db.session.rollback()
    return render_template(
        "error.html",
        code=code,
        message=messages.get(code, "Kuch galat hua.")
    ), code

CATEGORY_ICONS = {
    "Rice & Grains": "🍚", "Dal & Pulses": "🥣", "Edible Oil & Ghee": "🫒",
    "Salt, Sugar & Spices": "🧂", "Biscuits & Bakery": "🍪", "Snacks": "🍿", "Snacks & Biscuits": "🍪",
    "Dairy Products": "🥛", "Tea & Coffee": "☕", "Beverages": "🥤",
    "Instant & Packaged Food": "🍜", "Dry Fruits & Nuts": "🥜",
    "Personal Care": "🧴", "Household & Cleaning": "🧹", "Baby Care": "🍼",
}


@app.route("/")
def home():
    rows = (
        db.session.query(Category, db.func.count(Product.id))
        .outerjoin(Product, Product.category_id == Category.id)
        .group_by(Category.id)
        .order_by(Category.id)
        .all()
    )
    categories = [
        {"id": c.id, "name": c.name, "count": n, "icon": CATEGORY_ICONS.get(c.name, "🛒")}
        for c, n in rows
    ]
    featured = (
        Product.query.filter(Product.stock > 0)
        .order_by(Product.id.desc()).limit(4).all()
    )
    return render_template("index.html", categories=categories, featured=featured)


@app.route("/test-db")
@admin_required
def test_db():
    try:
        with db.engine.connect():
            return "✅ MySQL Database Connected Successfully!"
    except Exception as e:
        app.logger.error("DB connection failed: %s", e)
        return "❌ Database Connection Failed (details server log me hain)"


@app.route("/products")
def products():
    q = request.args.get("q", "").strip()
    category_id = request.args.get("category", type=int)

    query = Product.query

    if q:
        query = query.filter(Product.name.ilike(f"%{q}%"))
    if category_id:
        query = query.filter_by(category_id=category_id)

    recommendations = []
    rec_title = ""

    # Recommendations sirf tab, jab koi search/filter na ho
    if not q and not category_id:
        history_ids = []
        if current_user.is_authenticated:
            history_ids = [
                row[0] for row in
                db.session.query(OrderItem.product_id)
                .join(Order, Order.id == OrderItem.order_id)
                .filter(Order.user_id == current_user.id, Order.status != "Cancelled")
                .distinct().all()
            ]
        recommendations = safe_recommend(history_ids)
        rec_title = "🤖 Aapke liye AI picks" if history_ids else "🔥 Popular products"

    return render_template(
        "products.html",
        products=query.order_by(Product.name).all(),
        categories=Category.query.all(),
        q=q,
        selected_category=category_id,
        recommendations=recommendations,
        rec_title=rec_title
    )

@app.route("/add-to-cart/<int:product_id>", methods=["POST"])
@login_required
def add_to_cart(product_id):

    product = db.get_or_404(Product, product_id)

    stock = product.stock or 0
    if stock <= 0:
        flash(f"{product.name} abhi stock me nahi hai.", "error")
        return redirect(url_for("products"))

    user_cart = Cart.query.filter_by(user_id=current_user.id).first()

    if not user_cart:
        user_cart = Cart(user_id=current_user.id)
        db.session.add(user_cart)
        db.session.commit()

    cart_item = CartItem.query.filter_by(
        cart_id=user_cart.id,
        product_id=product.id
    ).first()

    if cart_item:
        if cart_item.quantity >= stock:
            flash(f"{product.name} ka sirf {stock} stock available hai.", "error")
            return redirect(url_for("cart"))
        cart_item.quantity += 1
    else:
        cart_item = CartItem(
            cart_id=user_cart.id,
            product_id=product.id,
            quantity=1
        )
        db.session.add(cart_item)

    db.session.commit()

    flash(f"{product.name} cart me add ho gaya!", "success")

    next_url = request.form.get("next", "")
    if is_safe_next(next_url):
        return redirect(next_url)
    return redirect(url_for("products"))

@app.route("/cart")
@login_required
def cart():

    user_cart = Cart.query.filter_by(user_id=current_user.id).first()

    cart_items = CartItem.query.filter_by(cart_id=user_cart.id).all() if user_cart else []
    total = sum(float(item.product.price) * item.quantity for item in cart_items)

    recommendations = safe_recommend([item.product_id for item in cart_items])

    return render_template(
        "cart.html",
        cart_items=cart_items,
        total=total,
        recommendations=recommendations,
        rec_title="🤖 Aapke cart ke saath ye bhi achha lagega"
    )

@app.route("/cart/update/<int:item_id>", methods=["POST"])
@login_required
def update_cart(item_id):
    item = db.get_or_404(CartItem, item_id)

    # Sirf apne cart ka item hi change ho sake
    if item.cart.user_id != current_user.id:
        flash("Ye item aapke cart me nahi hai.", "error")
        return redirect(url_for("cart"))

    action = request.form.get("action")

    if action == "increase":
        if item.quantity >= (item.product.stock or 0):
            flash(f"{item.product.name} ka itna hi stock available hai.", "error")
        else:
            item.quantity += 1
    elif action == "decrease":
        if item.quantity > 1:
            item.quantity -= 1
        else:
            db.session.delete(item)

    db.session.commit()
    return redirect(url_for("cart"))


@app.route("/cart/remove/<int:item_id>", methods=["POST"])
@login_required
def remove_from_cart(item_id):
    item = db.get_or_404(CartItem, item_id)

    if item.cart.user_id != current_user.id:
        flash("Ye item aapke cart me nahi hai.", "error")
        return redirect(url_for("cart"))

    db.session.delete(item)
    db.session.commit()

    flash("Item cart se hata diya.", "success")
    return redirect(url_for("cart"))

@app.route("/checkout", methods=["GET", "POST"])
@login_required
def checkout():
    user_cart = Cart.query.filter_by(user_id=current_user.id).first()

    if not user_cart or not user_cart.items:
        flash("Aapka cart khali hai.", "error")
        return redirect(url_for("cart"))

    cart_items = user_cart.items
    total = sum((item.product.price * item.quantity for item in cart_items), Decimal("0"))

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        phone = request.form.get("phone", "").strip()
        address = request.form.get("address", "").strip()

        if not full_name or not phone or not address:
            flash("Saari fields bharna zaroori hai.", "error")
            return redirect(url_for("checkout"))

        if not re.fullmatch(r"[0-9]{10}", phone):
            flash("Phone number 10 digit ka hona chahiye.", "error")
            return redirect(url_for("checkout"))

        # Products ko lock karke stock check karo, taaki 2 log ek saath last piece na kharid sakein
        Product.query.filter(Product.id.in_([i.product_id for i in cart_items])) \
            .order_by(Product.id).with_for_update().populate_existing().all()

        for item in cart_items:
            available = item.product.stock or 0
            if item.quantity > available:
                db.session.rollback()
                flash(f"{item.product.name} ka sirf {available} stock bacha hai.", "error")
                return redirect(url_for("cart"))

        order = Order(
            user_id=current_user.id,
            full_name=full_name,
            phone=phone,
            address=address,
            total_amount=total,
            payment_method="COD",
            status="Pending"
        )
        db.session.add(order)
        db.session.flush()   # order.id mil jaye

        for item in cart_items:
            db.session.add(OrderItem(
                order_id=order.id,
                product_id=item.product.id,
                product_name=item.product.name,
                price=item.product.price,
                quantity=item.quantity
            ))
            item.product.stock -= item.quantity

        for item in list(cart_items):
            db.session.delete(item)

        db.session.commit()

        return redirect(url_for("order_success", order_id=order.id))

    return render_template("checkout.html", cart_items=cart_items, total=total)


@app.route("/order-success/<int:order_id>")
@login_required
def order_success(order_id):
    order = db.get_or_404(Order, order_id)

    if order.user_id != current_user.id:
        flash("Ye order aapka nahi hai.", "error")
        return redirect(url_for("products"))

    return render_template("order_success.html", order=order)


@app.route("/orders")
@login_required
def orders():
    user_orders = (
        Order.query
        .filter_by(user_id=current_user.id)
        .order_by(Order.created_at.desc())
        .all()
    )
    return render_template("orders.html", orders=user_orders)


@app.route("/orders/<int:order_id>/cancel", methods=["POST"])
@login_required
def cancel_order(order_id):
    order = db.get_or_404(Order, order_id)

    if order.user_id != current_user.id:
        abort(403)

    if order.status not in ("Pending", "Confirmed"):
        flash("Ye order ab cancel nahi ho sakta.", "error")
        return redirect(url_for("orders"))

    restock_order(order)
    order.status = "Cancelled"
    db.session.commit()
    flash(f"Order #{order.id} cancel ho gaya.", "success")
    return redirect(url_for("orders"))

@app.route("/ask-ai", methods=["POST"])
def ask_ai():
    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()[:300]

    if not message:
        return jsonify({"reply": "Kuch likhiye to sahi 🙂", "products": []})

    try:
        return jsonify(answer_message(message))
    except Exception as e:
        app.logger.warning("Chatbot error: %s", e)
        return jsonify({"reply": "Abhi jawab nahi de pa raha, thodi der baad try karo.", "products": []})

ORDER_STATUSES = ["Pending", "Confirmed", "Out for Delivery", "Delivered", "Cancelled"]



@app.route("/admin")
@admin_required
def admin_dashboard():
    revenue = (
        db.session.query(db.func.coalesce(db.func.sum(Order.total_amount), 0))
        .filter(Order.status != "Cancelled")
        .scalar()
    )
    stats = {
        "products": Product.query.count(),
        "orders": Order.query.count(),
        "users": User.query.count(),
        "revenue": float(revenue),
        "low_stock": Product.query.filter(Product.stock <= 10).count(),
    }
    return render_template("admin_dashboard.html", stats=stats)


@app.route("/admin/products")
@admin_required
def admin_products():
    all_products = Product.query.order_by(Product.id.desc()).all()
    return render_template("admin_products.html", products=all_products)


@app.route("/admin/products/add", methods=["GET", "POST"])
@app.route("/admin/products/edit/<int:product_id>", methods=["GET", "POST"])
@admin_required
def admin_product_form(product_id=None):
    product = db.get_or_404(Product, product_id) if product_id else None
    all_categories = Category.query.all()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        category_id = request.form.get("category_id", type=int)
        price = request.form.get("price", type=float)
        stock = request.form.get("stock", type=int)
        description = request.form.get("description", "").strip()
        image_file = request.files.get("image_file")
        remove_image = request.form.get("remove_image") == "1"

        if (not name or category_id is None or price is None or price < 0
                or stock is None or stock < 0):
            flash("Name, category, price aur stock sahi bharo.", "error")
            return redirect(request.url)

        if len(name) > 150 or len(description) > 500:
            flash("Name 150 aur description 500 characters se zyada nahi ho sakte.", "error")
            return redirect(request.url)

        if not db.session.get(Category, category_id):
            flash("Ye category exist nahi karti.", "error")
            return redirect(request.url)

        # Image sabse aakhir me save hoti hai, taaki upar ke check fail hone par file na bache
        new_image = None
        if image_file and image_file.filename:
            new_image = save_product_image(image_file)
            if not new_image:
                flash("Sirf JPG, PNG ya WEBP image upload karo.", "error")
                return redirect(request.url)

        if product is None:
            product = Product()
            db.session.add(product)

        old_image = product.image

        product.name = name
        product.category_id = category_id
        product.price = Decimal(str(price)).quantize(Decimal("0.01"))
        product.stock = stock
        product.description = description
        if new_image:
            product.image = new_image
        elif remove_image:
            product.image = None

        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            delete_product_image(new_image)
            raise

        if old_image and old_image != product.image:
            delete_product_image(old_image)

        flash("Product save ho gaya.", "success")
        return redirect(url_for("admin_products"))

    return render_template(
        "admin_product_form.html",
        product=product,
        categories=all_categories
    )

@app.route("/admin/products/delete/<int:product_id>", methods=["POST"])
@admin_required
def admin_delete_product(product_id):
    product = db.get_or_404(Product, product_id)
    image_name = product.image
    try:
        CartItem.query.filter_by(product_id=product.id).delete()
        db.session.delete(product)
        db.session.commit()
        delete_product_image(image_name)
        flash("Product delete ho gaya.", "success")
    except IntegrityError:
        db.session.rollback()
        flash("Ye product purane orders me use hua hai, delete nahi ho sakta. Stock 0 kar do.", "error")
    return redirect(url_for("admin_products"))


@app.route("/admin/orders")
@admin_required
def admin_orders():
    all_orders = Order.query.order_by(Order.created_at.desc()).all()
    return render_template("admin_orders.html", orders=all_orders, statuses=ORDER_STATUSES)


@app.route("/admin/orders/<int:order_id>/status", methods=["POST"])
@admin_required
def admin_update_order(order_id):
    order = db.get_or_404(Order, order_id)
    new_status = request.form.get("status")

    if new_status not in ORDER_STATUSES:
        flash("Galat status.", "error")
        return redirect(url_for("admin_orders"))

    if order.status == "Cancelled" and new_status != "Cancelled":
        flash("Cancelled order ko dobara activate nahi kar sakte.", "error")
        return redirect(url_for("admin_orders"))

    # Cancel hone pe stock wapas add karo
    if new_status == "Cancelled" and order.status != "Cancelled":
        restock_order(order)

    order.status = new_status
    db.session.commit()
    flash(f"Order #{order.id} ka status '{new_status}' ho gaya.", "success")
    return redirect(url_for("admin_orders"))

@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("products"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not name or not email or not password:
            flash("Saari fields bharna zaroori hai.", "error")
            return redirect(url_for("register"))

        if not EMAIL_RE.match(email) or len(email) > 120 or len(name) > 100:
            flash("Sahi email aur naam daalo.", "error")
            return redirect(url_for("register"))

        if len(password) < 6:
            flash("Password kam se kam 6 characters ka rakho.", "error")
            return redirect(url_for("register"))

        if User.query.filter_by(email=email).first():
            flash("Ye email pehle se registered hai.", "error")
            return redirect(url_for("register"))

        user = User(name=name, email=email)
        user.set_password(password)
        db.session.add(user)
        try:
            db.session.commit()
        except IntegrityError:        # 2 requests ek saath aayi to
            db.session.rollback()
            flash("Ye email pehle se registered hai.", "error")
            return redirect(url_for("register"))

        flash("Account ban gaya! Ab login karo.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("products"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password):
            login_user(user)
            next_url = request.args.get("next") or request.form.get("next") or ""
            return redirect(next_url if is_safe_next(next_url) else url_for("products"))

        flash("Email ya password galat hai.", "error")
        return redirect(url_for("login", next=request.args.get("next")) if request.args.get("next") else url_for("login"))

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Logout ho gaye.", "success")
    return redirect(url_for("home"))

with app.app_context():
    db.create_all()

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG", "0") == "1")