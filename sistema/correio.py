"""
Envio de e-mail por SMTP, configurado por variável de ambiente:
SMTP_SERVIDOR, SMTP_PORTA (587), SMTP_USUARIO, SMTP_SENHA e SMTP_REMETENTE.

Sem as variáveis, o sistema segue como sempre foi: a senha aparece na tela e a
coordenação entrega em mãos. Um Gmail com senha de app é o suficiente pra
ligar. Erro daqui nunca derruba a operação: quem chama recebe a mensagem e
decide o que mostrar na tela.
"""

import os
import smtplib
import threading
from email.message import EmailMessage


def _config():
    servidor = os.environ.get("SMTP_SERVIDOR")
    usuario = os.environ.get("SMTP_USUARIO")
    senha = os.environ.get("SMTP_SENHA")
    if not (servidor and usuario and senha):
        return None
    return {
        "servidor": servidor,
        "porta": int(os.environ.get("SMTP_PORTA", "587")),
        "usuario": usuario,
        "senha": senha,
        "remetente": os.environ.get("SMTP_REMETENTE", usuario),
    }


def configurado() -> bool:
    return _config() is not None


def enviar(para: str, assunto: str, corpo: str) -> str | None:
    """Manda um e-mail agora. Devolve mensagem de erro, ou None se saiu."""
    cfg = _config()
    if cfg is None:
        return "o envio de e-mail não está configurado"
    if not para:
        return "a pessoa não tem e-mail na ficha"
    try:
        _entregar(cfg, [(para, assunto, corpo)])
        return None
    except Exception as erro:
        return f"o e-mail não saiu: {erro}"


def enviar_em_lote(mensagens: list[tuple[str, str, str]]) -> int:
    """
    Dispara vários e-mails numa thread, fora da requisição — demora dentro da
    requisição já derrubou o lote de acessos uma vez, o correio não vai
    repetir isso. Pula quem não tem e-mail; devolve quantos entraram na fila.
    """
    cfg = _config()
    fila = [m for m in mensagens if m[0]]
    if cfg is None or not fila:
        return 0
    threading.Thread(target=_entregar_calado, args=(cfg, fila), daemon=True).start()
    return len(fila)


def _entregar_calado(cfg, fila):
    # Thread de fundo não tem tela pra avisar; o e-mail aqui é cortesia.
    try:
        _entregar(cfg, fila)
    except Exception:
        pass


def _entregar(cfg, fila):
    with smtplib.SMTP(cfg["servidor"], cfg["porta"], timeout=15) as smtp:
        smtp.starttls()
        smtp.login(cfg["usuario"], cfg["senha"])
        for para, assunto, corpo in fila:
            mensagem = EmailMessage()
            mensagem["From"] = cfg["remetente"]
            mensagem["To"] = para
            mensagem["Subject"] = assunto
            mensagem.set_content(corpo)
            smtp.send_message(mensagem)
