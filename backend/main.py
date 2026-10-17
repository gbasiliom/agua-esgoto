import os
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from database import Base, engine
import models
import auth
import seguranca as seg
from migracao_auto import alinhar_colunas
from routers import (
    auth_router, chamados_router, usuarios_router, clientes_router,
    estoque_router, funcionarios_router, leituras_router, faturamento_router,
    contas_router, licitacoes_router, analise_eta_router, qualidade_router,
)

novas_colunas = alinhar_colunas(engine, Base)
if novas_colunas:
    print("Banco atualizado automaticamente (colunas novas):", ", ".join(novas_colunas))

EM_PRODUCAO = os.getenv("SIGA_ENV", "desenvolvimento").strip().lower() == "producao"

# Em produção a documentação interativa (/docs) fica desligada: ela é um mapa pronto da API para atacantes.
app = FastAPI(
    title="SIGA — Sistema Integrado de Gestão de Água e Esgoto",
    docs_url=None if EM_PRODUCAO else "/docs",
    redoc_url=None,
    openapi_url=None if EM_PRODUCAO else "/openapi.json",
)

# CORS: os apps (Android) e o painel (Windows) não passam pelo navegador, então não precisam.
# Só habilite se algum dia houver um site chamando a API: SIGA_CORS_ORIGENS=https://meusite.com.br
_origens = [o.strip() for o in os.getenv("SIGA_CORS_ORIGENS", "").split(",") if o.strip()]
if _origens:
    app.add_middleware(CORSMiddleware, allow_origins=_origens, allow_credentials=False,
                       allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"], allow_headers=["Authorization", "Content-Type"])

MAX_UPLOAD_BYTES = int(float(os.getenv("SIGA_MAX_UPLOAD_MB", "15")) * 1024 * 1024)


@app.middleware("http")
async def protecoes_http(request: Request, call_next):
    # Limite de tamanho de envio (fotos/laudos): corta antes de gastar memória/disco.
    if request.method in ("POST", "PUT", "PATCH"):
        tamanho = request.headers.get("content-length")
        if tamanho and tamanho.isdigit() and int(tamanho) > MAX_UPLOAD_BYTES * 8:  # várias fotos por chamado
            return JSONResponse(status_code=413, content={"detail": "Arquivo(s) grande(s) demais."})
    resposta = await call_next(request)
    resposta.headers["X-Content-Type-Options"] = "nosniff"
    resposta.headers["X-Frame-Options"] = "DENY"
    resposta.headers["Referrer-Policy"] = "no-referrer"
    resposta.headers["Cross-Origin-Resource-Policy"] = "same-origin"
    if request.url.path.startswith(("/auth", "/usuarios", "/uploads")):
        resposta.headers["Cache-Control"] = "no-store"
    if EM_PRODUCAO:
        resposta.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return resposta


PASTA_UPLOADS = os.path.abspath("uploads")
os.makedirs(os.path.join(PASTA_UPLOADS, "chamados"), exist_ok=True)


@app.get("/uploads/{caminho:path}", include_in_schema=False)
def baixar_upload(caminho: str, usuario: models.Usuario = Depends(auth.exigir_tipo("admin", "operador", "tecnico", "quimico"))):
    """Fotos e notas fiscais só para a equipe logada (antes qualquer pessoa com o link abria)."""
    alvo = os.path.abspath(os.path.join(PASTA_UPLOADS, caminho))
    if not alvo.startswith(PASTA_UPLOADS + os.sep) or not os.path.isfile(alvo):
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")
    return FileResponse(alvo)


app.include_router(auth_router.router)
app.include_router(chamados_router.router)
app.include_router(usuarios_router.router)
app.include_router(clientes_router.router)
app.include_router(estoque_router.router)
app.include_router(funcionarios_router.router)
app.include_router(leituras_router.router)
app.include_router(faturamento_router.router)
app.include_router(contas_router.router)
app.include_router(licitacoes_router.router)
app.include_router(analise_eta_router.router)
app.include_router(qualidade_router.router)


@app.get("/")
def raiz():
    return {"status": "API do sistema de água e esgoto no ar"}
