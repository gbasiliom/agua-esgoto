"""
Ponto de entrada pra empacotar o backend como .exe (PyInstaller).

O detalhe importante aqui: muda a pasta de trabalho pra pasta onde o
.exe de verdade está (não a pasta temporária que o PyInstaller usa por
baixo dos panos) — assim o banco de dados (siga.db) e a pasta de uploads
(fotos) ficam gravados do lado do .exe, de forma permanente, e não
somem quando o programa fecha.
"""
import os
import sys


def pasta_do_executavel():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


os.chdir(pasta_do_executavel())

if __name__ == "__main__":
    import uvicorn
    from main import app

    print("=" * 60)
    print("  SIGA — Backend rodando!")
    print("  Deixe esta janela aberta enquanto for usar o sistema.")
    print("  Endereço: http://localhost:8000")
    print("=" * 60)

    uvicorn.run(app, host="0.0.0.0", port=8000)
