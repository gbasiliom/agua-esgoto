import threading


def rodar_em_background(widget, funcao, ao_sucesso=None, ao_erro=None):
    """
    Roda `funcao()` numa thread separada (não trava a janela) e, quando
    terminar, agenda o callback de volta na thread principal do Tkinter
    (obrigatório — widgets não podem ser mexidos fora da thread principal).

    widget: qualquer widget vivo (usa o `.after()` dele pra voltar à thread principal)
    funcao: função sem argumentos que faz a chamada de API e retorna o resultado
    ao_sucesso: recebe o resultado da função, se tudo der certo
    ao_erro: recebe a exceção, se algo falhar
    """
    def alvo():
        try:
            resultado = funcao()
        except Exception as erro:
            # Python apaga a variável do 'except' ao sair do bloco, então
            # captura ela já como valor padrão do lambda (avaliado agora,
            # não depois) — senão dá "cannot access free variable".
            if ao_erro:
                widget.after(0, lambda e=erro: ao_erro(e))
            return
        if ao_sucesso:
            widget.after(0, lambda: ao_sucesso(resultado))

    threading.Thread(target=alvo, daemon=True).start()
