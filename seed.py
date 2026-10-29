"""Pehli baar chalao:  python seed.py
Categories, sample products aur admin user bana deta hai. Dobara chalane se duplicate nahi banta."""
import os
from getpass import getpass
from decimal import Decimal

from app import app, db
from models import User, Category, Product

# (category, [(name, price, stock, description)])
DATA = {
    "Rice & Grains": [
        ("Basmati Rice 1kg", 95, 100, "Long grain basmati chawal"),
        ("Sona Masoori Rice 1kg", 62, 120, "Daily use chawal"),
        ("Wheat Flour (Atta) 5kg", 245, 80, "Chakki fresh gehu ka atta"),
        ("Poha 500g", 38, 60, "Patla poha nashte ke liye"),
    ],
    "Dal & Pulses": [
        ("Toor Dal 1kg", 150, 90, "Arhar dal"),
        ("Moong Dal 1kg", 125, 70, "Dhuli moong dal"),
        ("Chana Dal 1kg", 105, 70, "Chana dal"),
        ("Masoor Dal 1kg", 98, 65, "Lal masoor dal"),
    ],
    "Edible Oil & Ghee": [
        ("Mustard Oil 1L", 165, 60, "Kachi ghani sarso tel"),
        ("Sunflower Oil 1L", 135, 75, "Refined sunflower oil"),
        ("Pure Ghee 500ml", 310, 40, "Desi ghee"),
    ],
    "Salt, Sugar & Spices": [
        ("Iodized Salt 1kg", 22, 150, "Namak"),
        ("Sugar 1kg", 46, 150, "Cheeni"),
        ("Turmeric Powder 200g", 48, 80, "Haldi powder masala"),
        ("Red Chilli Powder 200g", 62, 80, "Lal mirch masala"),
        ("Garam Masala 100g", 70, 60, "Garam masala"),
    ],
    "Dairy Products": [
        ("Full Cream Milk 1L", 68, 50, "Doodh"),
        ("Curd 400g", 40, 40, "Dahi"),
        ("Butter 100g", 58, 45, "Makhan"),
        ("Paneer 200g", 85, 30, "Fresh paneer"),
    ],
    "Tea & Coffee": [
        ("Tea Powder 250g", 120, 70, "Assam chai patti"),
        ("Instant Coffee 50g", 150, 40, "Coffee powder"),
    ],
    "Snacks & Biscuits": [
        ("Glucose Biscuit 200g", 20, 100, "Biscuit"),
        ("Namkeen Mix 400g", 90, 50, "Chatpata namkeen"),
    ],
}


def main():
    with app.app_context():
        db.create_all()

        for cname, items in DATA.items():
            cat = Category.query.filter_by(name=cname).first()
            if not cat:
                cat = Category(name=cname)
                db.session.add(cat)
                db.session.flush()
            for name, price, stock, desc in items:
                if not Product.query.filter_by(name=name).first():
                    db.session.add(Product(name=name, category_id=cat.id,
                                           price=Decimal(price), stock=stock, description=desc))
        db.session.commit()
        print("✅ Categories aur products ready.")

        email = os.environ.get("ADMIN_EMAIL", "admin@aibasket.com").lower()
        if User.query.filter_by(email=email).first():
            print(f"ℹ️  Admin {email} pehle se hai.")
            return
        password = os.environ.get("ADMIN_PASSWORD") or getpass(f"Admin ({email}) ka password set karo: ")
        if len(password) < 6:
            raise SystemExit("Password kam se kam 6 characters ka ho.")
        admin = User(name="Admin", email=email, is_admin=True)
        admin.set_password(password)
        db.session.add(admin)
        db.session.commit()
        print(f"✅ Admin ban gaya: {email}")


if __name__ == "__main__":
    main()
