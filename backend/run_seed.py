r"""
Ponto de entrada pra empacotar o "resetar senhas de teste" como .exe.

Mesmo cuidado do run_server.py: muda a pasta de trabalho pra pasta onde o
.exe de verdade está, ANTES de importar o seed_dados_teste — assim ele
mexe no MESMO siga.db que o SIGA-Backend.exe usa, não num banco separado
sem efeito nenhum.

IMPORTANTE: esse .exe precisa ficar na mesma pasta que o SIGA-Backend.exe
(ou seja, dentro de backend\dist\) — é assim que os dois acham o mesmo
banco de dados.
"""
import os
import sys
import traceback

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def pasta_do_executavel():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


os.chdir(pasta_do_executavel())

if __name__ == "__main__":
    try:
        print("=" * 60)
        print("  SIGA — Resetando usuários de teste...")
        print("=" * 60)
        sys.stdout.flush()

        import seed_dados_teste  # roda o script inteiro, na pasta certa

        print("\n" + "=" * 60)
        print("  Pronto! Login padrão do painel:")
        print("  admin@teste.com / 123456")
        print("=" * 60)

    except Exception:
        print("\n" + "=" * 60)
        print("  ERRO — não foi possível resetar. Detalhes abaixo:")
        print("=" * 60)
        traceback.print_exc()

    finally:
        input("\nPressione Enter pra fechar esta janela...")
