import threading
from kivy.clock import Clock


def rodar_em_background(funcao, ao_sucesso=None, ao_erro=None):
    """Roda `funcao()` fora da thread da interface e devolve o resultado via Clock."""
    def alvo():
        try:
            resultado = funcao()
        except Exception as erro:
            if ao_erro:
                Clock.schedule_once(lambda dt, e=erro: ao_erro(e))
            return
        if ao_sucesso:
            Clock.schedule_once(lambda dt: ao_sucesso(resultado))

    threading.Thread(target=alvo, daemon=True).start()
