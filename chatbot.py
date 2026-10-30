import re

from models import db, Product, Category
from recommender import recommend

GREETINGS = {"hi", "hello", "hey", "namaste", "namaskar", "hii", "helo"}
HELP_WORDS = {"help", "madad"}
PLAN_WORDS = {
    "rasan", "ration", "grocery", "groceries", "saman", "samaan", "basket",
    "budget", "monthly", "weekly", "hafte", "mahine", "aayega", "aayegi",
}
CHEAP_WORDS = {"sasta", "saste", "sastha", "cheap", "cheapest", "kam"}
POPULAR_WORDS = {"popular", "bestseller", "trending", "recommend", "suggest", "best"}

STOP_WORDS = {
    "the", "and", "for", "you", "are", "what", "show", "tell", "give", "need",
    "want", "have", "with", "please", "pls", "kya", "kaun", "kaunsa", "kitna",
    "kitne", "kitni", "dikhao", "dikha", "batao", "bata", "chahiye", "chahie",
    "dena", "mujhe", "mereko", "mera", "meri", "rate", "price", "daam", "dam",
    "cost", "available", "stock", "milega", "milegi", "hain", "mein", "sabse",
    "rupaye", "rupees", "rupee", "rupay", "wala", "wali", "wale", "aur", "tak",
    "hai", "ek", "do", "kuch", "koi", "mere", "liye", "aap", "tum", "main",
    "product", "products", "item", "items", "list", "dikhaiye", "bataiye",
    "lena", "kharidun", "kharidna", "sabhi", "saare",
}

NOISE = STOP_WORDS | GREETINGS | HELP_WORDS | PLAN_WORDS | CHEAP_WORDS | POPULAR_WORDS

# Hinglish -> product names me jo English words hain
SYNONYMS = {
    "chawal": "rice", "chaawal": "rice", "dudh": "milk", "doodh": "milk",
    "chai": "tea", "tel": "oil", "namak": "salt", "cheeni": "sugar",
    "chini": "sugar", "daal": "dal", "dahi": "curd", "makhan": "butter",
    "masala": "spice", "masale": "spice", "biscuits": "biscuit",
}

# Budget plan me in categories se ek-ek sasta product chuna jata hai
ESSENTIAL = [
    "Rice & Grains", "Dal & Pulses", "Edible Oil & Ghee",
    "Salt, Sugar & Spices", "Dairy Products", "Tea & Coffee",
]


def _card(p):
    return {
        "id": p.id,
        "name": p.name,
        "price": float(p.price),
        "stock": p.stock or 0,
        "category": p.category.name,
    }


def _reply(text, products=None):
    return {"reply": text, "products": [_card(p) for p in (products or [])]}


def _tokens(text):
    words = re.findall(r"[a-z]+", text.lower())
    out = []
    for w in words:
        w = SYNONYMS.get(w, w)
        if len(w) >= 3 and w not in NOISE:
            out.append(w)
    return out


def _amount(text):
    t = text.lower().replace(",", "")
    m = (
        re.search(r"(\d{2,6})\s*(?:rs|rupee|rupees|rupaye|rupay|inr|₹|/-|me\b|mein\b|tak\b|ka\b|ki\b)", t)
        or re.search(r"(?:rs\.?|₹|inr|budget)\s*(\d{2,6})", t)
    )
    return int(m.group(1)) if m else None


def _search(tokens, limit=6):
    """Naam > category > description ke weight se score karta hai.
    Word-boundary use hota hai, taaki 'rice' se 'price' ya 'tea' se 'steam' match na ho."""
    if not tokens:
        return []

    conds = []
    for t in tokens:
        like = f"%{t}%"
        conds += [
            Product.name.ilike(like),
            Category.name.ilike(like),
            Product.description.ilike(like),
        ]

    products = Product.query.join(Category).filter(db.or_(*conds)).all()

    def score(p):
        name, cat, desc = p.name.lower(), p.category.name.lower(), (p.description or "").lower()
        total = 0
        for t in tokens:
            pat = r"\b" + re.escape(t)
            if re.search(pat, name):
                total += 3
            if re.search(pat, cat):
                total += 2
            if re.search(pat, desc):
                total += 1
        return total

    scored = [(score(p), p) for p in products]
    scored = [(sc, p) for sc, p in scored if sc > 0]
    scored.sort(key=lambda x: (-x[0], float(x[1].price)))
    return [p for _, p in scored[:limit]]


def _budget_plan(budget):
    if budget < 50 or budget > 100000:
        return _reply("Budget 50 se 1,00,000 rupaye ke beech batao, jaise '500 rupaye me rasan'.")

    chosen, total = [], 0.0
    for cname in ESSENTIAL:
        p = (
            Product.query.join(Category)
            .filter(Category.name == cname, Product.stock > 0)
            .order_by(Product.price)
            .first()
        )
        if p and total + float(p.price) <= budget:
            chosen.append(p)
            total += float(p.price)

    if not chosen:
        return _reply(f"₹{budget} me basic rasan banana mushkil hai. Thoda budget badhake try karo.")

    left = budget - total
    return _reply(
        f"₹{budget} me ye basic rasan aa sakta hai. Total ₹{total:.0f}, ₹{left:.0f} bach gaye. "
        f"Har category ka sabse sasta in-stock product chuna hai:",
        chosen,
    )


def answer_message(message):
    text = message.lower().strip()
    words = set(re.findall(r"[a-z]+", text))
    tokens = _tokens(text)

    # 1. Greeting / help
    if words & GREETINGS and not tokens:
        return _reply("welcome! 😊 Main AI Basket assistant hu. Budget, rate ya product ke baare me pucho. "
                      "Jaise: '500 me one week ka rasan'.")
    if words & HELP_WORDS:
        return _reply("Main ye kar sakta hu: budget ke hisaab se rasan batana, product ka rate aur stock batana, "
                      "sabse sasta product dhundhna, aur popular products dikhana.")

    # 2. Budget plan
    budget = _amount(text)
    if budget and (words & PLAN_WORDS or not tokens):
        return _budget_plan(budget)

    # 3. Popular / recommend
    if words & POPULAR_WORDS and not tokens:
        picks = recommend([], limit=4)
        if picks:
            return _reply("Ye products sabse zyada pasand kiye ja rahe hain 🔥", picks)

    found = _search(tokens, limit=50 if words & CHEAP_WORDS else 6)

    # 4. Sabse sasta
    if words & CHEAP_WORDS:
        pool = [p for p in found if (p.stock or 0) > 0] if tokens else \
               Product.query.filter(Product.stock > 0).order_by(Product.price).limit(3).all()
        pool = sorted(pool, key=lambda p: float(p.price))[:3]
        if pool:
            return _reply("Sabse sasta options ye hain 💰", pool)
        return _reply("Is naam ka koi in-stock product nahi mila.")

    # 5. Product search (rate, stock, availability)
    if found:
        out_of_stock = [p.name for p in found if (p.stock or 0) <= 0]
        note = ""
        if out_of_stock:
            note = " (Kuch products abhi out of stock hain.)"
        return _reply(f"Ye products mile{note}:", found)

    # 6. Kuch samajh nahi aaya
    if tokens:
        return _reply("Is naam ka koi product nahi mila 😕 Dusre naam se try karo, jaise 'rice', 'dal', 'milk'.")
    return _reply("Mujhe samajh nahi aaya. Aise pooch ke dekho: '500 rupaye me rasan', 'milk ka rate', 'sabse sasta dal'.")