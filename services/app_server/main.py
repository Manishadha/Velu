import os, json
from fastapi import FastAPI, Request, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from starlette.templating import Jinja2Templates

# storage (JSONL or SQLite depending on env)
from services.app_server.store import append_task, recent_tasks
# security middleware (size/rate limits read env at request time)
from services.app_server.middleware import BodySizeLimitMiddleware, RateLimitMiddleware
from pydantic import BaseModel


class TaskIn(BaseModel):
    task: str
    payload: dict = {}


def create_app() -> FastAPI:
    app = FastAPI()

    @app.get("/health")
    def health():
        return {"ok": True, "app": "velu"}

    # security middleware
    app.add_middleware(BodySizeLimitMiddleware)
    app.add_middleware(RateLimitMiddleware)

    # CORS allowlist via env
    _origins = os.environ.get("CORS_ORIGINS", "")
    allowed = [o.strip() for o in _origins.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed or ["http://localhost", "http://127.0.0.1"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    # ---------- API ----------
    @app.options("/tasks")
    def tasks_preflight():
        return {}

    @app.post("/tasks")
    def accept_task(t: TaskIn):
        d = t.model_dump()
        append_task(d)
        return {"ok": True, "received": d}

    @app.get("/tasks")
    def list_tasks(limit: int = 50):
        return {"ok": True, "items": recent_tasks(limit=limit)}

    # ---------- UI ----------
    templates = Jinja2Templates(directory="services/app_server/templates")

    @app.get("/")
    def home_redirect():
        return RedirectResponse(url="/ui/tasks", status_code=307)

    @app.get("/ui/tasks")
    def ui_list_tasks(request: Request, limit: int = 50):
        items = recent_tasks(limit=limit)
        # pretty-print payload for the table
        for it in items:
            if isinstance(it.get("payload"), (dict, list)):
                it["payload"] = json.dumps(it["payload"], ensure_ascii=False)
        return templates.TemplateResponse("tasks.html", {"request": request, "items": items})

    @app.post("/ui/tasks")
    def ui_create_task(task: str = Form(...), payload: str = Form("{}")):
        try:
            data = json.loads(payload or "{}")
        except Exception:
            data = {"raw": payload}
        append_task({"task": task, "payload": data})
        return RedirectResponse(url="/ui/tasks", status_code=303)

    return app


# default instance for uvicorn / docker
app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
