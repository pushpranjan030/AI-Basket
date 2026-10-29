import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from sqlalchemy.orm import joinedload

from models import db, Product, Order, OrderItem


def _order_rows():
    """Cancelled orders ko chhodke saari (order_id, product_id, quantity)."""
    return (
        db.session.query(OrderItem.order_id, OrderItem.product_id, OrderItem.quantity)
        .join(Order, Order.id == OrderItem.order_id)
        .filter(Order.status != "Cancelled")
        .all()
    )


def _load_products_df():
    products = Product.query.options(joinedload(Product.category)).all()   # N+1 queries se bachao
    return pd.DataFrame([
        {
            "id": p.id,
            # category ka naam 2 baar, taaki same category ko zyada weight mile
            "text": f"{p.name} {p.category.name} {p.category.name} {p.description or ''}",
            "in_stock": (p.stock or 0) > 0,
        }
        for p in products
    ])


def _content_similarity(df):
    try:
        matrix = TfidfVectorizer(stop_words="english").fit_transform(df["text"])
        return cosine_similarity(matrix)
    except ValueError:
        return np.zeros((len(df), len(df)))


def _collab_similarity(df, rows):
    """Item-item similarity: kaun se products ek hi order me saath aaye."""
    if not rows:
        return None

    basket = pd.DataFrame(
        [(r.order_id, r.product_id) for r in rows],
        columns=["order_id", "product_id"]
    )
    basket["bought"] = 1

    matrix = basket.pivot_table(
        index="order_id", columns="product_id",
        values="bought", aggfunc="max", fill_value=0
    )
    matrix = matrix.reindex(columns=df["id"], fill_value=0)

    if matrix.shape[0] < 2:      # 2 se kam orders me pattern nahi bante
        return None

    return cosine_similarity(matrix.T.values)


def _popularity(df, rows):
    sold = {}
    for r in rows:
        sold[r.product_id] = sold.get(r.product_id, 0) + r.quantity

    scores = np.array([sold.get(pid, 0) for pid in df["id"]], dtype=float)
    return scores / scores.max() if scores.max() > 0 else scores


def recommend(product_ids, limit=4):
    """product_ids ke hisaab se best `limit` products (Product objects) wapas karta hai."""
    df = _load_products_df()
    if df.empty:
        return []

    ids = df["id"].tolist()
    position = {pid: i for i, pid in enumerate(ids)}
    seed = [position[p] for p in product_ids if p in position]

    rows = _order_rows()
    popular = _popularity(df, rows)

    if not seed:
        scores = popular.copy()                       # cold start
    else:
        content = _content_similarity(df)[seed].mean(axis=0)
        collab = _collab_similarity(df, rows)

        if collab is not None:
            scores = 0.5 * content + 0.4 * collab[seed].mean(axis=0) + 0.1 * popular
        else:
            scores = 0.9 * content + 0.1 * popular

    scores = np.array(scores, dtype=float)
    scores[seed] = -1                                 # jo already hai wo mat dikhao
    scores[~df["in_stock"].values] = -1               # out of stock mat dikhao

    ranked = [ids[i] for i in np.argsort(-scores) if scores[i] >= 0][:limit]
    if not ranked:
        return []

    found = {p.id: p for p in Product.query.filter(Product.id.in_(ranked)).all()}
    return [found[pid] for pid in ranked if pid in found]