import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from database import Base, engine
from routers import (
    auth_router, chamados_router, usuarios_router, clientes_router,
    estoque_router, funcionarios_router, leituras_router, faturamento_router,
    contas_router, licitacoes_router, analise_eta_router, qualidade_router,
)

Base.metadata.create_all(bind=engine)

app = FastAPI(title="SIGA — Sistema Integrado de Gestão de Água e Esgoto")

os.makedirs("uploads/chamados", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

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
