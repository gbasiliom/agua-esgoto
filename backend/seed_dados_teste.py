"""
Cria dados de teste direto no banco: 1 admin, 1 técnico, 1 morador (com
cadastro/endereço já completo) e 1 chamado de exemplo já aberto.

Pode rodar quantas vezes quiser — cada usuário só é criado se ainda não
existir (checagem individual), então é seguro rodar de novo pra completar
o que faltou, sem duplicar o que já tinha.

Uso:
    cd backend
    venv\\Scripts\\activate   (ou source venv/bin/activate)
    python seed_dados_teste.py
"""
from database import SessionLocal, Base, engine
import models
import auth

Base.metadata.create_all(bind=engine)
db = SessionLocal()

try:
    criou_algo = False

    # --- Admin ---
    admin = db.query(models.Usuario).filter(models.Usuario.email == "admin@teste.com").first()
    if not admin:
        admin = models.Usuario(
            nome="Admin Teste", email="admin@teste.com",
            senha_hash=auth.hash_senha("123456"), tipo="admin",
        )
        db.add(admin)
        db.commit()
        db.refresh(admin)
        criou_algo = True
        print("✅ Admin de teste criado.")
    else:
        admin.senha_hash = auth.hash_senha("123456")  # garante que a senha é sempre 123456
        db.commit()
        print("→ Admin de teste já existia (senha resetada pra 123456).")

    # --- Técnico ---
    tecnico = db.query(models.Usuario).filter(models.Usuario.telefone == "31999999999").first()
    if not tecnico:
        tecnico = models.Usuario(
            nome="Técnico Teste", telefone="31999999999",
            senha_hash=auth.hash_senha("123456"), tipo="tecnico", localidade="sede",
        )
        db.add(tecnico)
        db.commit()
        db.refresh(tecnico)
        criou_algo = True
        print("✅ Técnico de teste criado (localidade: sede).")
    else:
        tecnico.senha_hash = auth.hash_senha("123456")
        if not tecnico.localidade:
            tecnico.localidade = "sede"
        db.commit()
        print("→ Técnico de teste já existia (senha resetada pra 123456).")

    # --- Morador (usuário + cadastro/endereço completo) ---
    morador_usuario = db.query(models.Usuario).filter(models.Usuario.telefone == "31988888888").first()
    if not morador_usuario:
        morador_usuario = models.Usuario(
            nome="Morador Teste", telefone="31988888888",
            senha_hash=auth.hash_senha("123456"), tipo="cliente",
        )
        db.add(morador_usuario)
        db.commit()
        db.refresh(morador_usuario)
        criou_algo = True
        print("✅ Usuário do morador de teste criado.")
    else:
        morador_usuario.senha_hash = auth.hash_senha("123456")
        db.commit()
        print("→ Usuário do morador de teste já existia (senha resetada pra 123456).")

    cliente = db.query(models.Cliente).filter(models.Cliente.usuario_id == morador_usuario.id).first()
    if not cliente:
        cliente = models.Cliente(
            usuario_id=morador_usuario.id,
            nome="Morador Teste",
            documento="000.000.000-00",
            endereco="Rua Exemplo, 123",
            bairro="Centro",
            cidade="Conceição de Ipanema",
            hidrometro="HID-0001",
            categoria="residencial",
            localidade="sede",
            status_cadastro="aprovado",
            ativo=True,
        )
        db.add(cliente)
        db.commit()
        db.refresh(cliente)
        criou_algo = True
        print("✅ Cadastro/endereço do morador de teste criado (localidade: sede).")
    else:
        if not cliente.localidade:
            cliente.localidade = "sede"
            db.commit()
            print("→ Cadastro do morador de teste já existia (localidade atualizada pra 'sede').")
        else:
            print("→ Cadastro do morador de teste já existia.")

    # --- Chamado de exemplo ---
    chamado = db.query(models.Chamado).filter(models.Chamado.cliente_id == cliente.id).first()
    if not chamado:
        chamado = models.Chamado(
            cliente_id=cliente.id,
            tipo="vazamento",
            local_atendimento=cliente.localidade,
            descricao_problema="Vazamento na calçada em frente à casa",
            prioridade="alta",
            origem="app",
            status="aberto",
        )
        db.add(chamado)
        db.commit()
        db.refresh(chamado)
        criou_algo = True
        print(f"✅ Chamado de exemplo criado: #{chamado.id}")
    else:
        print(f"→ Já existia um chamado de exemplo: #{chamado.id}")

    print()
    if criou_algo:
        print("Pronto! Dados de teste disponíveis:\n")
    else:
        print("Nada novo pra criar — já estava tudo pronto:\n")

    print("Login do ADMIN (painel Windows):")
    print("  usuário: admin@teste.com")
    print("  senha:   123456\n")
    print("Login do TÉCNICO (app Android/PC):")
    print("  usuário: 31999999999")
    print("  senha:   123456\n")
    print("Login do MORADOR de teste (app cliente — já com cadastro/endereço completo):")
    print("  usuário: 31988888888")
    print("  senha:   123456\n")
    print(f"Chamado de exemplo: #{chamado.id} (vazamento, aberto)")
    print("→ Entra no painel Windows como admin e atribui esse chamado ao técnico pra testar o fluxo completo.")
finally:
    db.close()
