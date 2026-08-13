"""
Login para os testes de navegador.

Depois que o sistema passou a exigir login, os testes de layout, contraste e
captura de tela pararam de funcionar: todos caíam na tela de entrar. Este módulo
resolve isso num lugar só, em vez de repetir o formulário em três scripts.

Como a conta de teste é tratada:

  - Toda execução APAGA a conta anterior e cria uma nova com senha aleatória.
  - A senha existe só na memória do processo e nunca é gravada em arquivo.
  - Se o script morrer no meio, sobra uma conta com senha aleatória que ninguém
    conhece — inofensiva — e a execução seguinte a apaga.

Para remover na mão:  python criar_usuario.py --listar   (e depois apagar no banco)
"""

import secrets
import sys
from pathlib import Path

# Os testes rodam de dentro de testes/, então preciso apontar pra pasta de cima
# pra achar db.py e autenticacao.py.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import autenticacao  # noqa: E402
import db  # noqa: E402

LOGIN_TESTE = "teste-automatizado"


def preparar_admin() -> str:
    """Cria a conta de teste e devolve a senha. Apaga a anterior, se houver."""
    conexao = db.conectar()
    try:
        senha = secrets.token_urlsafe(18)
        conexao.execute("DELETE FROM usuario WHERE login = ?", (LOGIN_TESTE,))
        conexao.execute(
            "INSERT INTO usuario (login, senha_hash, papel) VALUES (?,?,'admin')",
            (LOGIN_TESTE, autenticacao.hash_da_senha(senha)),
        )
        conexao.commit()
        return senha
    finally:
        conexao.close()


def remover_admin() -> None:
    conexao = db.conectar()
    try:
        conexao.execute("DELETE FROM usuario WHERE login = ?", (LOGIN_TESTE,))
        conexao.commit()
    finally:
        conexao.close()


def entrar(pagina, base: str, senha: str) -> None:
    """Faz login no navegador. Estoura se não entrar, pra não testar às cegas."""
    pagina.goto(f"{base}/entrar", wait_until="networkidle")
    pagina.fill("#login", LOGIN_TESTE)
    pagina.fill("#senha", senha)
    pagina.click("button[type=submit]")
    pagina.wait_for_load_state("networkidle")

    if "/entrar" in pagina.url:
        raise RuntimeError(
            "não consegui entrar no sistema com a conta de teste. "
            "O teste seria feito na tela de login, e passaria medindo a tela errada."
        )
