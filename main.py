from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from db import engine, SessionLocal
from models import Base, Item

app = FastAPI(title="Shopping List")

templates = Jinja2Templates(directory="templates")

@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    with SessionLocal() as db:
        items = db.execute(select(Item).order_by(Item.id.desc())).scalars().all()
    return templates.TemplateResponse("index.html", {"request": request, "items": items})

@app.post("/items")
def add_item(name: str = Form(...)):
    with SessionLocal() as db:
        db.add(Item(name=name))
        db.commit()
    return RedirectResponse(url="/", status_code=303)

@app.post("/items/{item_id}/delete")
def delete_item(item_id: int):
    with SessionLocal() as db:
        item = db.get(Item, item_id)
        if item:
            db.delete(item)
            db.commit()
    return RedirectResponse(url="/", status_code=303)

@app.get("/api/items")
def api_list_items():
    with SessionLocal() as db:
        items = db.execute(select(Item).order_by(Item.id.desc())).scalars().all()
    return [{"id": i.id, "name": i.name} for i in items]

@app.post("/api/items")
def api_add_item(payload: dict):
    name = (payload.get("name") or "").strip()
    if not name:
        return {"error": "name is required"}
    with SessionLocal() as db:
        db.add(Item(name=name))
        db.commit()
    return {"ok": True}
