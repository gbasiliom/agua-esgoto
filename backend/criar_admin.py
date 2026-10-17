"""Cria (ou redefine a senha de) um administrador, SEM dados de teste.
Use na primeira instalação, já que o cadastro público não cria mais admin.

    python criar_admin.py                 (pergunta nome, login e senha)

Rode na pasta backend, com o MESMO banco/chaves do servidor (mesma pasta e mesmo .env).
"""
import getpass
import sys

import auth
import models
import seguranca as seg
from database import SessionLocal, engine, Base


def main():
    Base.metadata.create_all(bind=engine)
    nome = input("Nome do administrador: ").strip()
    login = input("E-mail do administrador (é o login e recebe os códigos de segurança): ").strip().lower()
    if not nome or not seg.e_mail_valido(login):
        sys.exit("Nome e um e-mail válido são obrigatórios.")
    senha = getpass.getpass("Senha (mín. 8 caracteres, com letra e número): ")
    erros = seg.problemas_senha(senha, nome, login)
    if erros:
        sys.exit("A senha precisa " + "; ".join(erros) + ".")
    if senha != getpass.getpass("Repita a senha: "):
        sys.exit("As senhas não conferem.")

    db = SessionLocal()
    try:
        u = db.query(models.Usuario).filter(
            (models.Usuario.email == login) | (models.Usuario.telefone == login)).first()
        if u:
            if u.tipo != "admin":
                sys.exit(f"Já existe um usuário '{u.nome}' com esse login e ele NÃO é admin. Use outro login.")
            u.senha_hash = auth.hash_senha(senha)
            u.nome = nome
            u.trocar_senha = False
            u.falhas_login = 0
            u.bloqueado_ate = None
            u.token_versao = (u.token_versao or 0) + 1  # derruba sessões antigas
            print("Administrador existente: senha redefinida.")
        else:
            db.add(models.Usuario(nome=nome, senha_hash=auth.hash_senha(senha), tipo="admin", email=login,
                                  senha_alterada_em=seg.agora_utc()))
            print("Administrador criado.")
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    main()
