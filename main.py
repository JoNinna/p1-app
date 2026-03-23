import logging
import os
import uuid
from functools import lru_cache

import jwt
import requests
from fastapi import FastAPI, Request, Form, HTTPException, Depends, status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

from db import engine, SessionLocal
from models import Base, Item

print("Loaded RBAC version of main.py file")

app = FastAPI(title="Shopping List")
templates = Jinja2Templates(directory="templates")
security = HTTPBearer(auto_error=False)

OIDC_ISSUER = os.getenv("OIDC_ISSUER", "http://auth.local/realms/devops-lvlup")
OIDC_CLIENT_ID = os.getenv("OIDC_CLIENT_ID", "shopping-app")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("shopping-app")


@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)
    logger.info("app started | issuer=%s client_id=%s", OIDC_ISSUER, OIDC_CLIENT_ID)


def get_correlation_id(request: Request) -> str:
    return request.headers.get("x-correlation-id") or str(uuid.uuid4())


@lru_cache(maxsize=1)
def fetch_oidc_config():
    resp = requests.get(f"{OIDC_ISSUER}/.well-known/openid-configuration", timeout=5)
    resp.raise_for_status()
    return resp.json()


@lru_cache(maxsize=1)
def fetch_signing_keys():
    oidc_config = fetch_oidc_config()
    jwks_uri = oidc_config["jwks_uri"]
    resp = requests.get(jwks_uri, timeout=5)
    resp.raise_for_status()
    jwks = resp.json()

    keys_by_kid = {}
    for key in jwks["keys"]:
        kid = key.get("kid")
        if kid:
            keys_by_kid[kid] = jwt.algorithms.RSAAlgorithm.from_jwk(key)
    return keys_by_kid


def validate_token(token: str):
    oidc_config = fetch_oidc_config()
    keys_by_kid = fetch_signing_keys()

    try:
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")
        signing_key = keys_by_kid.get(kid)

        if signing_key is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Signing key not found",
            )

        payload = jwt.decode(
            token,
            signing_key,
            algorithms=["RS256"],
            issuer=oidc_config["issuer"],
            options={"verify_aud": False},
        )
        return payload

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )


def get_user_from_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    correlation_id = get_correlation_id(request)

    # 1. Încearcă mai întâi Bearer token-ul, dacă există
    if credentials and credentials.scheme.lower() == "bearer":
        payload = validate_token(credentials.credentials)

        username = (
            payload.get("preferred_username")
            or payload.get("email")
            or payload.get("sub")
        )

        roles = (
            payload.get("resource_access", {})
            .get(OIDC_CLIENT_ID, {})
            .get("roles", [])
        )

        user_context = {
            "username": username,
            "roles": roles,
            "correlation_id": correlation_id,
        }

        request.state.user = user_context
        return user_context

    # 2. Fallback: citește headerele trimise de oauth2-proxy prin ingress
    username = (
        request.headers.get("x-auth-request-preferred-username")
        or request.headers.get("x-auth-request-email")
        or request.headers.get("x-auth-request-user")
    )

    groups_header = request.headers.get("x-auth-request-groups", "")
    raw_groups = [g.strip() for g in groups_header.split(",") if g.strip()]

    roles = []
    for group in raw_groups:
        prefix = f"role:{OIDC_CLIENT_ID}:"
        if group.startswith(prefix):
            roles.append(group[len(prefix):])

    if username:
        user_context = {
            "username": username,
            "roles": roles,
            "correlation_id": correlation_id,
        }
        request.state.user = user_context
        return user_context

    logger.warning(
        "unauthorized | correlation_id=%s path=%s method=%s reason=missing_identity",
        correlation_id,
        request.url.path,
        request.method,
    )
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing authentication context",
    )

def require_roles(*allowed_roles):
    def checker(user=Depends(get_user_from_token)):
        user_roles = user["roles"]
        if not any(role in user_roles for role in allowed_roles):
            logger.warning(
                "forbidden | correlation_id=%s user=%s roles=%s required_roles=%s",
                user["correlation_id"],
                user["username"],
                user_roles,
                list(allowed_roles),
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden",
            )
        return user

    return checker


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if request.url.path.startswith("/api/"):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    with SessionLocal() as db:
        items = db.execute(select(Item).order_by(Item.id.desc())).scalars().all()
    return templates.TemplateResponse("index.html", {"request": request, "items": items})


@app.post("/items")
def add_item(
    request: Request,
    name: str = Form(...),
    user=Depends(require_roles("writer", "admin")),
):
    with SessionLocal() as db:
        db.add(Item(name=name))
        db.commit()

    logger.info(
        "allowed | correlation_id=%s user=%s roles=%s method=%s path=%s status=%s",
        user["correlation_id"],
        user["username"],
        user["roles"],
        request.method,
        request.url.path,
        303,
    )
    return RedirectResponse(url="/", status_code=303)


@app.post("/items/{item_id}/delete")
def delete_item(
    item_id: int,
    request: Request,
    user=Depends(require_roles("admin")),
):
    with SessionLocal() as db:
        item = db.get(Item, item_id)
        if item:
            db.delete(item)
            db.commit()

    logger.info(
        "allowed | correlation_id=%s user=%s roles=%s method=%s path=%s status=%s",
        user["correlation_id"],
        user["username"],
        user["roles"],
        request.method,
        request.url.path,
        303,
    )
    return RedirectResponse(url="/", status_code=303)


@app.get("/api/items")
def api_list_items(
    request: Request,
    user=Depends(require_roles("reader", "writer", "admin")),
):
    with SessionLocal() as db:
        items = db.execute(select(Item).order_by(Item.id.desc())).scalars().all()

    logger.info(
        "allowed | correlation_id=%s user=%s roles=%s method=%s path=%s status=%s",
        user["correlation_id"],
        user["username"],
        user["roles"],
        request.method,
        request.url.path,
        200,
    )
    return [{"id": i.id, "name": i.name} for i in items]


@app.post("/api/items", status_code=201)
def api_add_item(
    payload: dict,
    request: Request,
    user=Depends(require_roles("writer", "admin")),
):
    name = (payload.get("name") or "").strip()
    if not name:
        return JSONResponse(status_code=400, content={"error": "name is required"})

    with SessionLocal() as db:
        db.add(Item(name=name))
        db.commit()

    logger.info(
        "allowed | correlation_id=%s user=%s roles=%s method=%s path=%s status=%s",
        user["correlation_id"],
        user["username"],
        user["roles"],
        request.method,
        request.url.path,
        201,
    )
    return {"ok": True}


@app.delete("/api/items/{item_id}")
def api_delete_item(
    item_id: int,
    request: Request,
    user=Depends(require_roles("admin")),
):
    with SessionLocal() as db:
        item = db.get(Item, item_id)
        if item:
            db.delete(item)
            db.commit()

    logger.info(
        "allowed | correlation_id=%s user=%s roles=%s method=%s path=%s status=%s",
        user["correlation_id"],
        user["username"],
        user["roles"],
        request.method,
        request.url.path,
        200,
    )
    return {"ok": True, "deleted_id": item_id}
