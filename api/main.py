import asyncio
import hashlib
import hmac
import json
import os
import time
import uuid
from decimal import Decimal
from typing import Any
from urllib.parse import parse_qsl

import aiofiles
import aiohttp
import bleach
import magic
from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sqlalchemy import or_, select
from sqlalchemy import or_, select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from bot.config import settings
from db.engine import get_session
from db.models.chat import ChatMessage
from db.models.product import CurrencyType, DealStatus, MarketplaceDeal, Product, PromoCode, DiscountType
from db.models.notification import InAppNotification
from db.models.user import UserWalletChain
from services import marketplace_dispute_service
from services.marketplace_ecommerce import MarketplaceEcommerceService
from services.marketplace_notifications import (
    get_bot,
    notify_deal_completed,
    notify_deal_created,
    notify_deal_delivered,
    notify_deal_paid,
    notify_new_message,
    notify_stars_purchase,
)

app = FastAPI(title="P2P Marketplace API", version="1.0.0")

# Setup Rate Limiting
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------


def validate_init_data(init_data: str, bot_token: str) -> bool:
    """Validate Telegram WebApp initData HMAC signature."""
    try:
        parsed_data = dict(parse_qsl(init_data))
        if "hash" not in parsed_data:
            return False
        hash_val = parsed_data.pop("hash")
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed_data.items()))
        secret_key = hmac.new(
            key=b"WebAppData",
            msg=bot_token.encode(),
            digestmod=hashlib.sha256,
        ).digest()
        # Verify expiration (max 24h)
        try:
            auth_date = int(parsed_data.get("auth_date", 0))
        except ValueError:
            return False
        if time.time() - auth_date > 86400:
            return False

        calculated_hash = hmac.new(
            key=secret_key,
            msg=data_check_string.encode(),
            digestmod=hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(calculated_hash, hash_val)
    except Exception:
        return False


def _parse_tg_user(init_data: str) -> dict:
    """Extract user dict from initData string."""
    parsed = dict(parse_qsl(init_data))
    user_json = parsed.get("user", "{}")
    try:
        return json.loads(user_json)
    except Exception:
        return {}


async def get_current_user(authorization: str = Header(None)) -> dict:
    """FastAPI dependency: validates Telegram initData and returns parsed user."""
    if not authorization or not authorization.startswith("tma "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    init_data = authorization[4:]
    if not validate_init_data(init_data, settings.BOT_TOKEN.get_secret_value()):
        raise HTTPException(status_code=403, detail="Invalid Telegram InitData")
    user = _parse_tg_user(init_data)
    return {
        "user_id": user.get("id"),
        "first_name": user.get("first_name", ""),
        "username": user.get("username", ""),
    }


async def get_current_user_optional(authorization: str = Header(None)) -> dict | None:
    """Same as get_current_user but returns None instead of raising for missing header."""
    if not authorization or not authorization.startswith("tma "):
        return None
    init_data = authorization[4:]
    if not validate_init_data(init_data, settings.BOT_TOKEN.get_secret_value()):
        return None
    user = _parse_tg_user(init_data)
    return {
        "user_id": user.get("id"),
        "first_name": user.get("first_name", ""),
        "username": user.get("username", ""),
    }


# ---------------------------------------------------------------------------
# Telegram Bot API helper
# ---------------------------------------------------------------------------


async def _create_stars_invoice_link(
    product: Product,
    payload: str,
    amount: int | None = None,
) -> str:
    """Call Telegram Bot API createInvoiceLink to generate a Stars payment link.

    Args:
        product: The Product being purchased.
        payload: Opaque payload string (product ID) returned on successful payment.

    Returns:
        Invoice URL string.

    Raises:
        RuntimeError: If Telegram API returns an error.
    """
    token = settings.BOT_TOKEN
    url = f"https://api.telegram.org/bot{token}/createInvoiceLink"
    body = {
        "title": product.title[:32],
        "description": (product.description or "Digital product")[:255],
        "payload": payload,
        "provider_token": "",  # Empty = Telegram Stars
        "currency": "XTR",
        "prices": [{"label": product.title[:32], "amount": amount if amount is not None else int(product.price)}],
    }
    async with (
        aiohttp.ClientSession() as session,
        session.post(url, json=body, timeout=aiohttp.ClientTimeout(total=10)) as resp,
    ):
        data = await resp.json()
    if not data.get("ok"):
        raise RuntimeError(
            f"Telegram createInvoiceLink failed: {data.get('description', 'unknown error')}"
        )
    return data["result"]


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@app.get("/api/health")
async def health_check() -> dict:
    """Service health probe."""
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Products — public read
# ---------------------------------------------------------------------------


@app.get("/api/products")
async def get_products(
    q: str | None = Query(None),
    category: str | None = Query(None),
    sort: str | None = Query(None, description="price_asc | price_desc | newest"),
    currency_type: str | None = Query(None, description="XTR | FIAT | CRYPTO"),
    session: AsyncSession = Depends(get_session),
) -> list:
    """List active products with optional search, category, currency, and sort filters."""
    from db.models.user import User
    stmt = (
        select(Product)
        .options(joinedload(Product.seller))
        .join(Product.seller)
        .where(Product.is_active.is_(True))
        .where(User.is_shadowbanned.is_(False))
    )
    if q:
        stmt = stmt.where(or_(Product.title.ilike(f"%{q}%"), Product.description.ilike(f"%{q}%")))
    if category and hasattr(Product, "category"):
        stmt = stmt.where(getattr(Product, "category") == category)
    if currency_type:
        stmt = stmt.where(Product.currency_type == currency_type)
    if sort == "price_asc":
        stmt = stmt.order_by(Product.price.asc())
    elif sort == "price_desc":
        stmt = stmt.order_by(Product.price.desc())
    elif sort == "rating_desc":
        from db.models.user import User
        # Calculate avg rating and sort descending, fallback to review count
        stmt = stmt.order_by(
            (func.coalesce(User.rating_sum, 0) / func.coalesce(func.nullif(User.review_count, 0), 1)).desc(),
            User.review_count.desc()
        )
    else:
        order_col = (
            Product.created_at.desc() if hasattr(Product, "created_at") else Product.id.desc()
        )
        # Always order by is_promoted first, unless price_asc/price_desc is selected
        if sort not in ("price_asc", "price_desc"):
            stmt = stmt.order_by(Product.is_promoted.desc(), order_col)
        else:
            stmt = stmt.order_by(order_col)

    result = await session.execute(stmt)
    products = result.scalars().all()
    return [_serialize_product(p) for p in products]


@app.get("/api/products/{product_id}")
async def get_product(product_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    """Get a single product by ID."""
    result = await session.execute(
        select(Product).options(joinedload(Product.seller)).where(Product.id == product_id)
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return _serialize_product(product)


def _serialize_product(p: Product) -> dict:
    """Serialize a Product ORM instance to a JSON-safe dict."""
    rating_avg = 5.0
    reviews_count = 0
    is_verified_seller = False
    if getattr(p, "seller", None):
        reviews_count = p.seller.review_count
        if reviews_count > 0:
            rating_avg = round(float(p.seller.rating_sum) / float(reviews_count), 1)
        is_verified_seller = p.seller.is_verified_seller

    return {
        "id": str(p.id),
        "seller_id": p.seller_id,
        "title": p.title,
        "description": p.description,
        "price": float(p.price),
        "currency_type": p.currency_type,
        "fiat_currency": p.fiat_currency,
        "crypto_asset": p.crypto_asset,
        "crypto_chain": p.crypto_chain,
        "crypto_network": p.crypto_network,
        "is_digital": p.is_digital,
        "category": getattr(p, "category", None),
        "is_active": p.is_active,
        "image_urls": getattr(p, "image_urls", []),
        "seller_rating": rating_avg,
        "seller_reviews_count": reviews_count,
        "is_verified_seller": is_verified_seller,
    }


# ---------------------------------------------------------------------------
# Products — seller write
# ---------------------------------------------------------------------------


class CreateProductRequest(BaseModel):
    """Request body for product creation."""

    title: str
    description: str | None = None
    price: Decimal
    currency_type: str  # XTR | FIAT | CRYPTO
    fiat_currency: str | None = None
    crypto_asset: str | None = None
    crypto_chain: WalletChain | None = None
    crypto_network: str | None = None
    is_digital: bool = True
    category: str | None = None


@app.post("/api/products", status_code=201)
@limiter.limit("5/minute")
async def create_product(
    request: Request,
    body: CreateProductRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Create a new product listing (seller only).

    Args:
        body: Product fields from the seller.
        current_user: Authenticated Telegram user.
        session: DB session.

    Returns:
        Serialized new Product.

    Raises:
        HTTPException 422: Invalid currency/price combination.
    """
    if body.price <= 0:
        raise HTTPException(status_code=422, detail="Price must be positive")
    if body.currency_type not in ("XTR", "FIAT", "CRYPTO"):
        raise HTTPException(status_code=422, detail="currency_type must be XTR, FIAT, or CRYPTO")

    user = await session.get(User, current_user["user_id"])
    if user and user.is_shadowbanned:
        raise HTTPException(status_code=403, detail="Your account is restricted due to frequent disputes.")

    # Security: Sanitize inputs (XSS prevention)
    clean_title = bleach.clean(body.title, tags=[], strip=True)
    clean_desc = bleach.clean(
        body.description or "", tags=["b", "i", "u", "em", "strong", "br"], strip=True
    )

    product = await MarketplaceEcommerceService.create_product(
        session=session,
        seller_id=current_user["user_id"],
        title=clean_title,
        description=clean_desc,
        price=body.price,
        currency_type=CurrencyType(body.currency_type),
        fiat_currency=body.fiat_currency,
        crypto_asset=body.crypto_asset,
        crypto_chain=body.crypto_chain,
        crypto_network=body.crypto_network,
        is_digital=body.is_digital,
    )
    await session.commit()
    await session.refresh(product)
    return _serialize_product(product)


class UpdateProductRequest(BaseModel):
    """Request body for partial product update."""

    title: str | None = None
    description: str | None = None
    price: Decimal | None = None
    is_active: bool | None = None
    category: str | None = None


@app.patch("/api/products/{product_id}")
async def update_product(
    product_id: str,
    body: UpdateProductRequest,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Partially update a product (owner only).

    Raises:
        HTTPException 404: Product not found.
        HTTPException 403: Not the owner.
    """
    result = await session.execute(
        select(Product).where(Product.id == product_id).with_for_update()
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    if product.seller_id != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="You are not the owner of this product")

    if body.title is not None:
        product.title = bleach.clean(body.title, tags=[], strip=True)
    if body.description is not None:
        product.description = bleach.clean(
            body.description, tags=["b", "i", "u", "em", "strong", "br"], strip=True
        )
    if body.price is not None:
        product.price = body.price
    if body.is_active is not None:
        product.is_active = body.is_active
    if body.category is not None:
        product.category = body.category

    session.add(product)
    await session.commit()
    await session.refresh(product)
    return _serialize_product(product)


@app.post("/api/products/{product_id}/images", status_code=200)
async def upload_product_images(
    product_id: str,
    files: list[UploadFile] = File(...),
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Upload up to 5 images for a product (owner only)."""
    if len(files) > 5:
        raise HTTPException(status_code=400, detail="Maximum 5 images allowed")

    result = await session.execute(
        select(Product).where(Product.id == product_id).with_for_update()
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    if product.seller_id != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="You are not the owner of this product")

    # Limit to 5 images total (existing + new)
    current_images = getattr(product, "image_urls", [])
    if len(current_images) + len(files) > 5:
        raise HTTPException(status_code=400, detail="Cannot exceed 5 images total")

    upload_dir = "/app/uploads"
    os.makedirs(upload_dir, exist_ok=True)

    max_file_size = 5 * 1024 * 1024  # 5MB
    allowed_extensions = {".jpg", ".jpeg", ".png", ".webp"}

    new_urls = []
    for file in files:
        content = await file.read()

        # 1. Check file size
        if len(content) > max_file_size:
            raise HTTPException(status_code=400, detail=f"File {file.filename} exceeds 5MB limit")

        # 2. Check extension
        ext = os.path.splitext(file.filename or "")[1].lower()
        if ext not in allowed_extensions:
            raise HTTPException(status_code=400, detail=f"Extension {ext} not allowed")

        # 3. Verify actual content type using magic bytes
        mime = magic.from_buffer(content, mime=True)
        if not mime.startswith("image/"):
            raise HTTPException(
                status_code=400, detail=f"File {file.filename} is not a valid image"
            )

        unique_filename = f"{uuid.uuid4().hex}{ext}"
        filepath = os.path.join(upload_dir, unique_filename)

        async with aiofiles.open(filepath, "wb") as out_file:
            await out_file.write(content)

        new_urls.append(f"/uploads/{unique_filename}")

    # Combine and save
    product.image_urls = current_images + new_urls
    session.add(product)
    await session.commit()
    await session.refresh(product)

    return _serialize_product(product)


@app.delete("/api/products/{product_id}", status_code=204)
async def delete_product(
    product_id: str,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Soft-delete (deactivate) a product (owner only).

    Raises:
        HTTPException 404: Product not found.
        HTTPException 403: Not the owner.
    """
    result = await session.execute(
        select(Product).where(Product.id == product_id).with_for_update()
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    if product.seller_id != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="You are not the owner of this product")
    product.is_active = False
    session.add(product)
    await session.commit()


@app.get("/api/seller/products")
async def get_seller_products(
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list:
    """Get all products (including inactive) belonging to the current seller."""
    result = await session.execute(
        select(Product)
        .options(joinedload(Product.seller))
        .where(Product.seller_id == current_user["user_id"])
        .order_by(Product.is_active.desc())
    )
    return [_serialize_product(p) for p in result.scalars().all()]


# ---------------------------------------------------------------------------
# Stars Invoice
# ---------------------------------------------------------------------------


class CreateInvoiceRequest(BaseModel):
    promo_code: str | None = None

@app.post("/api/products/{product_id}/invoice")
async def create_stars_invoice(
    product_id: str,
    body: CreateInvoiceRequest | None = None,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Create a Telegram Stars invoice link for a product.

    Args:
        product_id: UUID of the product to purchase.
        current_user: Authenticated buyer.
        session: DB session.

    Returns:
        Dict with invoice_url for openInvoice().

    Raises:
        HTTPException 404: Product not found.
        HTTPException 422: Product is not XTR-priced.
        HTTPException 502: Telegram API failure.
    """
    result = await session.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    user = await session.get(User, current_user["user_id"])
    if user and user.is_shadowbanned:
        raise HTTPException(status_code=403, detail="Your account is restricted due to frequent disputes.")

    if current_user["user_id"] == product.seller_id:
        raise HTTPException(status_code=400, detail="Cannot buy your own product")
    if product.currency_type != "XTR":
        raise HTTPException(status_code=422, detail="This product does not support Stars payment")

    final_amount = product.price
    if body and body.promo_code:
        from sqlalchemy.sql import func
        from db.models.product import PromoCode, DiscountType
        
        stmt_promo = select(PromoCode).where(
            func.lower(PromoCode.code) == body.promo_code.lower(),
            PromoCode.seller_id == product.seller_id
        ).with_for_update()
        
        promo = (await session.execute(stmt_promo)).scalar_one_or_none()
        if not promo:
            raise HTTPException(status_code=400, detail="Invalid promo code")
        if promo.expires_at and promo.expires_at < func.now():
            raise HTTPException(status_code=400, detail="Promo code has expired")
        if promo.max_uses and promo.current_uses >= promo.max_uses:
            raise HTTPException(status_code=400, detail="Promo code usage limit reached")
            
        if promo.discount_type == DiscountType.percentage:
            final_amount = final_amount - (final_amount * promo.discount_value) / 100
        else:
            final_amount = final_amount - promo.discount_value
            
        if final_amount < 0:
            final_amount = Decimal("0.00")
            
        promo.current_uses += 1
        await session.commit()
    
    # We pass the promo code in payload to confirm it later
    promo_str = f":{body.promo_code}" if body and body.promo_code else ""
    payload = f"{product_id}:{current_user['user_id']}{promo_str}"
    
    try:
        invoice_url = await _create_stars_invoice_link(product, payload, int(final_amount))
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {"invoice_url": invoice_url}


@app.get("/api/notifications")
async def get_notifications(
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Get in-app notifications for the user."""
    stmt = select(InAppNotification).where(
        InAppNotification.user_id == current_user["user_id"]
    ).order_by(InAppNotification.created_at.desc()).limit(50)
    
    result = await session.execute(stmt)
    notifications = result.scalars().all()
    
    return [
        {
            "id": str(n.id),
            "type": n.type,
            "title": n.title,
            "message": n.message,
            "is_read": n.is_read,
            "created_at": n.created_at.isoformat(),
        }
        for n in notifications
    ]


@app.post("/api/notifications/{notif_id}/read")
async def mark_notification_read(
    notif_id: str,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Mark a notification as read."""
    result = await session.execute(
        select(InAppNotification).where(InAppNotification.id == notif_id)
    )
    notif = result.scalar_one_or_none()
    
    if not notif or notif.user_id != current_user["user_id"]:
        raise HTTPException(status_code=404, detail="Notification not found")
        
    notif.is_read = True
    await session.commit()
    
    return {"status": "ok"}


@app.get("/api/seller/analytics")
async def get_seller_analytics(
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Get basic analytics for the logged-in seller."""
    seller_id = current_user["user_id"]
    
    # 1. Total successful deals (completed)
    deals_stmt = select(MarketplaceDeal).where(
        MarketplaceDeal.seller_id == seller_id,
        MarketplaceDeal.status == DealStatus.completed
    )
    deals_result = await session.execute(deals_stmt)
    deals = deals_result.scalars().all()
    
    total_xtr = sum(d.amount for d in deals if d.currency_type == "XTR")
    total_fiat = sum(d.amount for d in deals if d.currency_type == "FIAT")
    total_crypto = sum(d.amount for d in deals if d.currency_type == "CRYPTO")
    
    # 2. Active products
    products_stmt = select(func.count(Product.id)).where(
        Product.seller_id == seller_id,
        Product.is_active.is_(True)
    )
    active_count = (await session.execute(products_stmt)).scalar() or 0

    return {
        "successful_deals_count": len(deals),
        "total_revenue": {
            "XTR": float(total_xtr),
            "FIAT": float(total_fiat),
            "CRYPTO": float(total_crypto),
        },
        "active_products_count": active_count,
    }


@app.post("/api/products/{product_id}/boost/invoice")
async def create_product_boost_invoice(
    product_id: str,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Create a Telegram Stars invoice link to boost a product.
    
    Costs 50 XTR for 24 hours of promotion.
    """
    result = await session.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    if current_user["user_id"] != product.seller_id:
        raise HTTPException(status_code=403, detail="Only the seller can boost their product")

    # The payload MUST uniquely identify this as a boost payment.
    payload = f"boost:{product.id}"
    price_xtr = 50

    try:
        invoice_url = await _create_stars_invoice_link(product, payload, price_xtr, title=f"Boost {product.title}", description="Boost your product for 24 hours in the catalog.")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return {"invoice_url": invoice_url}


@app.post("/api/products/{product_id}/boost/confirm")
async def confirm_product_boost(
    product_id: str,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Mock endpoint to confirm a boost payment was successful.
    
    In production, this is done automatically via Telegram Webhook (successful_payment).
    """
    result = await session.execute(select(Product).where(Product.id == product_id).with_for_update())
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    if current_user["user_id"] != product.seller_id:
        raise HTTPException(status_code=403, detail="Unauthorized")

    product.is_promoted = True
    product.promoted_until = func.now() + timedelta(hours=24)
    
    await session.commit()
    
    return {"status": "ok", "message": "Product boosted successfully"}


@app.post("/api/deals/stars-confirm")
async def confirm_stars_deal(
    body: dict[str, Any],
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Confirm a successful Stars payment and create a completed deal.

    Called by the frontend after openInvoice() resolves with status='paid'.

    Args:
        body: Must contain product_id and telegram_payment_charge_id.
        current_user: Authenticated buyer.
        session: DB session.

    Returns:
        Created deal dict.
    """
    product_id = body.get("product_id")
    charge_id = body.get("telegram_payment_charge_id", "")

    result = await session.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    deal = MarketplaceDeal(
        product_id=product.id,
        buyer_id=current_user["user_id"],
        seller_id=product.seller_id,
        amount=product.price,
        currency_type=product.currency_type,
        status=DealStatus.paid,  # Stars are instant — no escrow wait
        telegram_payment_charge_id=charge_id,
    )
    session.add(deal)
    await session.commit()
    await session.refresh(deal)

    # Fire-and-forget: notify seller of Stars purchase
    asyncio.create_task(
        notify_stars_purchase(
            get_bot(),
            seller_id=product.seller_id,
            buyer_first_name=current_user.get("first_name", "Someone"),
            deal_id=str(deal.id),
            product_title=product.title,
            stars=float(product.price),
        )
    )

    return {"id": str(deal.id), "status": deal.status, "amount": float(deal.amount)}


# ---------------------------------------------------------------------------
# Deals
# ---------------------------------------------------------------------------


class CreateDealRequest(BaseModel):
    """Request body for fiat/crypto deal creation."""

    product_id: str
    promo_code: str | None = None


@app.post("/api/deals")
async def create_deal(
    body: CreateDealRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    user = await session.get(User, current_user["user_id"])
    if user and user.is_shadowbanned:
        raise HTTPException(status_code=403, detail="Your account is restricted due to frequent disputes.")

    try:
        deal = await MarketplaceEcommerceService.create_deal(
            session=session,
            product_id=uuid.UUID(body.product_id),
            buyer_id=current_user["user_id"],
            promo_code_str=body.promo_code,
        )
        await session.commit()
        await session.refresh(deal)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    # Fire-and-forget: notify seller of new escrow deal
    currency_label = (
        f"{deal.product.fiat_currency or 'USD'}"
        if deal.currency_type == "FIAT"
        else deal.product.crypto_asset or "CRYPTO"
    )
    asyncio.create_task(
        notify_deal_created(
            get_bot(),
            seller_id=deal.seller_id,
            buyer_first_name=current_user.get("first_name", "Someone"),
            deal_id=str(deal.id),
            product_title=deal.product.title,
            amount=float(deal.amount),
            currency=currency_label,
        )
    )

    return {"id": str(deal.id), "status": deal.status, "amount": float(deal.amount)}


@app.get("/api/deals")
async def get_my_deals(
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """Get all deals where the current user is buyer or seller."""
    uid = current_user["user_id"]
    stmt = (
        select(MarketplaceDeal, Product)
        .join(Product, MarketplaceDeal.product_id == Product.id)
        .where(or_(MarketplaceDeal.buyer_id == uid, MarketplaceDeal.seller_id == uid))
        .order_by(MarketplaceDeal.id.desc())
    )
    result = await session.execute(stmt)
    return [
        {
            "id": str(deal.id),
            "status": deal.status,
            "amount": float(deal.amount),
            "currency_type": deal.currency_type,
            "product_title": product.title,
            "role": "buyer" if deal.buyer_id == uid else "seller",
            "created_at": deal.created_at.isoformat() if deal.created_at else None,
            "dispute_reason": deal.dispute_reason,
            "dispute_opened_at": deal.dispute_opened_at.isoformat() if deal.dispute_opened_at else None,
            "dispute_resolution": deal.dispute_resolution,
        }
        for deal, product in result.all()
    ]


@app.get("/api/deals/{deal_id}")
async def get_deal(
    deal_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Get a specific deal with payment details."""
    deal = await MarketplaceEcommerceService.get_deal(session, uuid.UUID(deal_id))
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    if current_user["user_id"] not in (deal.buyer_id, deal.seller_id):
        raise HTTPException(status_code=403, detail="Unauthorized")

    resp = {
        "id": str(deal.id),
        "status": deal.status,
        "amount": float(deal.amount),
        "currency_type": deal.currency_type,
    }

    if deal.currency_type == "CRYPTO" and deal.escrow_wallet_address:
        resp.update(
            {
                "blockchain": deal.blockchain,
                "network": deal.network,
                "escrow_wallet_address": deal.escrow_wallet_address,
                "tx_hash_deposit": deal.tx_hash_deposit,
                "tx_hash_release": deal.tx_hash_release,
            }
        )
    elif deal.currency_type == "FIAT":
        resp.update(
            {
                "payment_method": "Sberbank",
                "payment_account": "4276 1234 5678 9012",
                "payment_name": "Ivan I.",
            }
        )

    return resp


@app.post("/api/deals/{deal_id}/pay")
async def mark_deal_paid(
    deal_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Buyer confirms fiat payment was sent."""
    result = await session.execute(
        select(MarketplaceDeal).where(MarketplaceDeal.id == deal_id).with_for_update()
    )
    deal = result.scalar_one_or_none()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    if deal.buyer_id != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="Only the buyer can mark this deal as paid")

    if deal.status != DealStatus.created:
        raise HTTPException(status_code=409, detail=f"Deal already in status: {deal.status}")
    deal.status = DealStatus.paid
    session.add(deal)
    await session.commit()

    # Fetch product for notification context
    prod_result = await session.execute(select(Product).where(Product.id == deal.product_id))
    product = prod_result.scalar_one_or_none()
    if product:
        asyncio.create_task(
            notify_deal_paid(
                get_bot(),
                seller_id=deal.seller_id,
                deal_id=str(deal.id),
                product_title=product.title,
                amount=float(deal.amount),
                currency=deal.currency_type,
            )
        )

    return {"status": "success", "message": "Deal marked as paid. Seller notified."}


# ---------------------------------------------------------------------------
# Reviews
# ---------------------------------------------------------------------------


class CreateReviewRequest(BaseModel):
    """Request body for creating a review."""

    rating: int
    comment: str | None = None


@app.post("/api/deals/{deal_id}/review")
async def create_deal_review(
    deal_id: str,
    body: CreateReviewRequest,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Leave a review for a completed deal."""
    if not 1 <= body.rating <= 5:
        raise HTTPException(status_code=422, detail="Rating must be between 1 and 5")

    result = await session.execute(select(MarketplaceDeal).where(MarketplaceDeal.id == deal_id))
    deal = result.scalar_one_or_none()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    if deal.buyer_id != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="Only the buyer can leave a review")

    # Assuming any paid or completed deal can be reviewed
    if deal.status not in (DealStatus.paid, DealStatus.delivered, DealStatus.completed):
        raise HTTPException(status_code=400, detail="Can only review completed/paid deals")

    # Check if review already exists
    from db.models.user import User

    rev_result = await session.execute(
        select(ProductReview).where(ProductReview.deal_id == deal.id)
    )
    if rev_result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Review already exists for this deal")

    # Create review
    review = ProductReview(
        deal_id=deal.id,
        reviewer_id=deal.buyer_id,
        seller_id=deal.seller_id,
        rating=body.rating,
        comment=body.comment,
    )
    session.add(review)

    # Update seller rating
    user_result = await session.execute(
        select(User).where(User.telegram_id == deal.seller_id).with_for_update()
    )
    seller = user_result.scalar_one_or_none()
    if seller:
        seller.rating_sum += body.rating
        seller.review_count += 1
        session.add(seller)

    await session.commit()

    return {"status": "success", "message": "Review submitted successfully"}


# ---------------------------------------------------------------------------
# Marketplace Deal Lifecycle (Phase 7)
# ---------------------------------------------------------------------------


@app.post("/api/deals/{deal_id}/deliver")
async def deliver_deal(
    deal_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Seller marks the deal as delivered/sent."""
    user_id = current_user["user_id"]

    deal = await MarketplaceEcommerceService.get_deal(session, deal_id, for_update=True)
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    if deal.seller_id != user_id:
        raise HTTPException(status_code=403, detail="Only seller can mark as delivered")

    try:
        await MarketplaceEcommerceService.deliver_deal(session, deal)
        await session.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Notify buyer
    bot = get_bot()
    asyncio.create_task(
        notify_deal_delivered(
            bot,
            buyer_id=deal.buyer_id,
            deal_id=str(deal.id),
            product_title=deal.product.title,
        )
    )

    return {"status": "success", "new_status": deal.status}


@app.post("/api/deals/{deal_id}/complete")
async def complete_deal(
    deal_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Buyer confirms receipt and completes the deal."""
    user_id = current_user["user_id"]

    deal = await MarketplaceEcommerceService.get_deal(session, deal_id, for_update=True)
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    if deal.buyer_id != user_id:
        raise HTTPException(status_code=403, detail="Only buyer can complete the deal")

    try:
        await MarketplaceEcommerceService.complete_deal(session, deal)
        await session.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Notify seller
    bot = get_bot()
    asyncio.create_task(
        notify_deal_completed(
            bot,
            seller_id=deal.seller_id,
            deal_id=str(deal.id),
            product_title=deal.product.title,
        )
    )

    return {"status": "success", "new_status": deal.status}


# ---------------------------------------------------------------------------
# Marketplace Chat (Phase 7)
# ---------------------------------------------------------------------------


class SendMessageRequest(BaseModel):
    text: str


@app.get("/api/deals/{deal_id}/messages")
async def get_deal_messages(
    deal_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """Fetch chat history for a marketplace deal."""
    user_id = current_user["user_id"]

    # Verify user is participant
    stmt_deal = select(MarketplaceDeal).where(MarketplaceDeal.id == deal_id)
    res_deal = await session.execute(stmt_deal)
    deal = res_deal.scalar_one_or_none()

    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    if user_id not in (deal.buyer_id, deal.seller_id):
        raise HTTPException(status_code=403, detail="Not a participant")

    # Fetch messages
    stmt_msg = (
        select(ChatMessage)
        .where(ChatMessage.deal_id == deal_id)
        .order_by(ChatMessage.created_at.asc())
    )
    res_msg = await session.execute(stmt_msg)
    messages = res_msg.scalars().all()

    return [
        {
            "id": str(m.id),
            "sender_id": m.sender_id,
            "text": m.message_text,
            "created_at": m.created_at.isoformat(),
        }
        for m in messages
    ]


@app.post("/api/deals/{deal_id}/messages")
@limiter.limit("30/minute")
async def send_deal_message(
    request: Request,
    deal_id: uuid.UUID,
    body: SendMessageRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Send a chat message in a marketplace deal."""
    user_id = current_user["user_id"]

    if len(body.text) > 2000:
        raise HTTPException(status_code=400, detail="Message too long")
    body.text = bleach.clean(body.text, tags=[], strip=True)

    stmt_deal = (
        select(MarketplaceDeal)
        .where(MarketplaceDeal.id == deal_id)
        .options(joinedload(MarketplaceDeal.product))
    )
    res_deal = await session.execute(stmt_deal)
    deal = res_deal.scalar_one_or_none()

    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    if user_id not in (deal.buyer_id, deal.seller_id):
        raise HTTPException(status_code=403, detail="Not a participant")

    # Create message
    msg = ChatMessage(
        deal_id=deal_id,
        sender_id=user_id,
        message_text=body.text,
    )
    session.add(msg)
    await session.commit()

    # Notify recipient
    recipient_id = deal.seller_id if user_id == deal.buyer_id else deal.buyer_id

    # We need the sender's name for the notification
    # For now, let's just use "Buyer" or "Seller" or try to fetch from User model if needed.
    # Actually, we can just say "The other party".
    sender_role = "Buyer" if user_id == deal.buyer_id else "Seller"

    bot = get_bot()
    asyncio.create_task(
        notify_new_message(
            bot,
            recipient_id=recipient_id,
            sender_name=sender_role,
            deal_id=str(deal.id),
            product_title=deal.product.title,
        )
    )

    return {"status": "success", "message_id": str(msg.id)}


# ---------------------------------------------------------------------------
# Dispute endpoints (Phase 10)
# ---------------------------------------------------------------------------


class OpenDisputeRequest(BaseModel):
    """Request body for opening a marketplace dispute."""

    reason: str


class ResolveDisputeRequest(BaseModel):
    """Request body for admin dispute resolution."""

    resolution: str  # "buyer" | "seller"
    comment: str = ""


@app.post("/api/deals/{deal_id}/dispute")
@limiter.limit("5/minute")
async def open_dispute(
    request: Request,
    deal_id: uuid.UUID,
    body: OpenDisputeRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Open a dispute on a marketplace deal.

    Only the buyer or seller of the deal may open a dispute.
    The deal must be in ``paid`` or ``delivered`` status,
    and at least 15 minutes must have passed since deal creation.
    """
    reason = bleach.clean(body.reason, tags=[], strip=True)
    if not reason or len(reason) > 800:
        raise HTTPException(status_code=400, detail="Reason must be 1–800 characters")

    try:
        result = await marketplace_dispute_service.open_marketplace_dispute(
            session,
            deal_id=str(deal_id),
            initiator_id=current_user["user_id"],
            reason=reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return result


@app.get("/api/admin/marketplace-disputes")
async def list_marketplace_disputes(
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, Any]]:
    """Return a paginated list of marketplace deals currently in dispute.

    Admin-only. Returns deals ordered by dispute_opened_at ascending
    (oldest first — serve longest-waiting cases first).
    """
    if current_user["user_id"] not in settings.ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Admin access required")

    stmt = (
        select(MarketplaceDeal)
        .where(MarketplaceDeal.status == DealStatus.dispute)
        .options(joinedload(MarketplaceDeal.product))
        .order_by(MarketplaceDeal.dispute_opened_at.asc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(stmt)
    deals = result.scalars().all()

    return [
        {
            "deal_id": str(d.id),
            "product_title": d.product.title,
            "buyer_id": d.buyer_id,
            "seller_id": d.seller_id,
            "amount": float(d.amount),
            "currency": d.currency_type.value,
            "dispute_reason": d.dispute_reason,
            "dispute_opened_at": d.dispute_opened_at.isoformat() if d.dispute_opened_at else None,
        }
        for d in deals
    ]


@app.post("/api/admin/users/{target_user_id}/unban")
async def unban_user(
    target_user_id: int,
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    """Unban a shadowbanned user and reset dispute counts."""
    if current_user["user_id"] not in settings.ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Admin access required")

    from db.models.user import User
    user = await session.get(User, target_user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_shadowbanned = False
    user.dispute_count_buyer = 0
    user.dispute_count_seller = 0
    await session.commit()

    return {"status": "ok", "message": f"User {target_user_id} unbanned"}


@app.post("/api/admin/marketplace-disputes/{deal_id}/resolve")
async def resolve_dispute(
    deal_id: uuid.UUID,
    body: ResolveDisputeRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Resolve a marketplace dispute as an admin.

    Accepted resolutions:
    - ``buyer``  — refund escrowed funds to buyer (on-chain or Stars refund).
    - ``seller`` — release escrowed funds to seller.
    """
    if current_user["user_id"] not in settings.ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Admin access required")

    resolution = body.resolution.strip().lower()
    comment = bleach.clean(body.comment, tags=[], strip=True)[:500]

    if resolution not in {"buyer", "seller"}:
        raise HTTPException(status_code=400, detail="resolution must be 'buyer' or 'seller'")

    bot = get_bot()
    try:
        result = await marketplace_dispute_service.resolve_marketplace_dispute(
            session,
            bot,
            deal_id=str(deal_id),
            admin_id=current_user["user_id"],
            resolution=resolution,  # type: ignore[arg-type]
            comment=comment,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return result


@app.get("/api/referral/stats")
async def get_referral_stats(
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Get referral statistics for the current user."""
    from db.models.user import User
    from sqlalchemy import select, func

    stmt = select(User).where(User.telegram_id == current_user["user_id"])
    user = (await session.execute(stmt)).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    stmt_count = select(func.count(User.telegram_id)).where(User.referred_by_id == current_user["user_id"])
    referred_count = (await session.execute(stmt_count)).scalar_one() or 0

    return {
        "referral_balance": float(user.referral_balance),
        "referred_users": referred_count,
        "referral_link": f"https://t.me/{settings.MASTER_BOT_USERNAME}?start=ref_{current_user['user_id']}"
    }

# ── Promo Codes ────────────────────────────────────────────────────────
class CreatePromoCodeRequest(BaseModel):
    code: str
    discount_type: str  # "percentage" or "fixed"
    discount_value: float
    max_uses: int | None = None

@app.post("/api/promo-codes")
async def create_promo_code(
    body: CreatePromoCodeRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    from db.models.product import PromoCode, DiscountType
    
    if body.discount_type not in ["percentage", "fixed"]:
        raise HTTPException(status_code=400, detail="Invalid discount type")
        
    code_val = body.code.strip().upper()
    if len(code_val) < 3:
        raise HTTPException(status_code=400, detail="Code must be at least 3 characters")
        
    promo = PromoCode(
        seller_id=current_user["user_id"],
        code=code_val,
        discount_type=DiscountType(body.discount_type),
        discount_value=Decimal(str(body.discount_value)),
        max_uses=body.max_uses,
    )
    session.add(promo)
    await session.commit()
    
    return {
        "id": promo.id,
        "code": promo.code,
        "discount_type": promo.discount_type,
        "discount_value": float(promo.discount_value)
    }

class ValidatePromoCodeRequest(BaseModel):
    code: str
    product_id: str

@app.post("/api/promo-codes/validate")
async def validate_promo_code(
    body: ValidatePromoCodeRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    from db.models.product import PromoCode, DiscountType, Product
    from sqlalchemy.sql import func
    
    # Get product to get seller
    stmt_prod = select(Product).where(Product.id == body.product_id)
    product = (await session.execute(stmt_prod)).scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
        
    stmt = select(PromoCode).where(
        func.lower(PromoCode.code) == body.code.strip().lower(),
        PromoCode.seller_id == product.seller_id
    )
    promo = (await session.execute(stmt)).scalar_one_or_none()
    if not promo:
        raise HTTPException(status_code=404, detail="Invalid promo code")
        
    if promo.expires_at and promo.expires_at < func.now():
        raise HTTPException(status_code=400, detail="Promo code has expired")
    if promo.max_uses and promo.current_uses >= promo.max_uses:
        raise HTTPException(status_code=400, detail="Promo code usage limit reached")
        
    return {
        "valid": True,
        "discount_type": promo.discount_type,
        "discount_value": float(promo.discount_value)
    }

@app.get("/api/promo-codes")
async def get_my_promo_codes(
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    from db.models.product import PromoCode
    
    stmt = select(PromoCode).where(PromoCode.seller_id == current_user["user_id"])
    result = await session.execute(stmt)
    codes = result.scalars().all()
    
    return [
        {
            "id": p.id,
            "code": p.code,
            "discount_type": p.discount_type,
            "discount_value": float(p.discount_value),
            "max_uses": p.max_uses,
            "current_uses": p.current_uses,
        }
        for p in codes
    ]
