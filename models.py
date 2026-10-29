from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

# =========================
# USER MODEL
# =========================

class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(15))
    address = db.Column(db.String(255))
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

# =========================
# CATEGORY MODEL
# =========================

class Category(db.Model):
    __tablename__ = "categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.String(255))

    products = db.relationship(
        "Product",
        backref="category",
        lazy=True
    )


# =========================
# PRODUCT MODEL
# =========================

class Product(db.Model):
    __tablename__ = "products"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)

    category_id = db.Column(
        db.Integer,
        db.ForeignKey("categories.id"),
        nullable=False
    )

    price = db.Column(db.Numeric(10, 2), nullable=False)
    stock = db.Column(db.Integer, default=0)
    description = db.Column(db.String(500))
    image = db.Column(db.String(255))


# =========================
# CART MODEL
# =========================

class Cart(db.Model):
    __tablename__ = "cart"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, unique=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    user = db.relationship("User", backref=db.backref("cart", uselist=False))
    items = db.relationship("CartItem", backref="cart", cascade="all, delete-orphan")

# =========================
# CART ITEM MODEL
# =========================

class CartItem(db.Model):
    __tablename__ = "cart_items"
    __table_args__ = (db.UniqueConstraint("cart_id", "product_id", name="uq_cart_product"),)

    id = db.Column(db.Integer, primary_key=True)

    cart_id = db.Column(
        db.Integer,
        db.ForeignKey("cart.id"),
        nullable=False
    )

    product_id = db.Column(
        db.Integer,
        db.ForeignKey("products.id"),
        nullable=False
    )

    quantity = db.Column(
        db.Integer,
        nullable=False,
        default=1
    )

    product = db.relationship(
        "Product",
        backref="cart_items"
    )

# =========================
# ORDER MODEL
# =========================

class Order(db.Model):
    __tablename__ = "orders"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False
    )

    full_name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(15), nullable=False)
    address = db.Column(db.String(255), nullable=False)

    total_amount = db.Column(db.Numeric(10, 2), nullable=False)
    payment_method = db.Column(db.String(30), default="COD")
    status = db.Column(db.String(30), default="Pending")

    created_at = db.Column(
        db.DateTime,
        server_default=db.func.now()
    )

    user = db.relationship("User", backref="orders")
    items = db.relationship(
        "OrderItem",
        backref="order",
        cascade="all, delete-orphan"
    )


# =========================
# ORDER ITEM MODEL
# =========================

class OrderItem(db.Model):
    __tablename__ = "order_items"

    id = db.Column(db.Integer, primary_key=True)

    order_id = db.Column(
        db.Integer,
        db.ForeignKey("orders.id"),
        nullable=False
    )

    product_id = db.Column(
        db.Integer,
        db.ForeignKey("products.id"),
        nullable=False
    )

    # Order ke time ka naam aur price save hota hai,
    # taaki baad me product ka price badle to purane orders na badlein
    product_name = db.Column(db.String(150), nullable=False)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)