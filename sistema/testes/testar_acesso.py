"""
Confere quem pode abrir o que. É o teste de segurança do login.

Este é o teste mais importante que existe aqui, e o motivo é simples: quando eu
escrevi a lista de rotas liberadas pro jogador, eu tinha colocado o painel da
modalidade nela pensando "é só leitura, não faz mal". Faz. O painel tem o bloco
"Ligar esta semana", com nome completo, nível de risco e telefone do responsável
de quem está faltando. Eu ia publicar isso pra turma inteira sem perceber.

O que ele prova, em ordem de importância:
  1. Anônimo não abre nada além da tela de entrar.
  2. Jogador NÃO abre painel, lista de pessoas, chamada nem configurações.
  3. O painel não devolve telefone nem rótulo de risco pra jogador.
  4. Admin abre tudo.
  5. Senha errada não entra, e a resposta não revela se o login existe.
  6. Sair encerra a sessão de verdade.

Precisa do sistema rodando. Ele cria as contas que usa e apaga no fim.
"""

import http.cookiejar
import re
import secrets
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import autenticacao  # noqa: E402
import db  # noqa: E402

BASE = "http://127.0.0.1:5000"

LOGIN_ADMIN = "teste-acesso-admin"
LOGIN_JOGADOR = "teste-acesso-jogador"

falhas = []


def checar(rotulo, condicao, detalhe=""):
    print(f"  [{'OK  ' if condicao else 'FALHA'}] {rotulo}"
          + (f" -- {detalhe}" if detalhe and not condicao else ""))
    if not condicao:
        falhas.append(rotulo)


def preparar_contas():
    """Cria admin e jogador de teste. O jogador é vinculado a alguém real."""
    conexao = db.conectar()
    try:
        pessoa = conexao.execute(
            """SELECT p.id FROM pessoa p JOIN matricula ma ON ma.pessoa_id = p.id
               GROUP BY p.id ORDER BY p.id LIMIT 1"""
        ).fetchone()

        senhas = {}
        for login, papel, pessoa_id in [
            (LOGIN_ADMIN, "admin", None),
            (LOGIN_JOGADOR, "jogador", pessoa["id"] if pessoa else None),
        ]:
            senha = secrets.token_urlsafe(18)
            conexao.execute("DELETE FROM usuario WHERE login = ?", (login,))
            conexao.execute(
                "INSERT INTO usuario (login, senha_hash, papel, pessoa_id) "
                "VALUES (?,?,?,?)",
                (login, autenticacao.hash_da_senha(senha), papel, pessoa_id),
            )
            senhas[login] = senha
        conexao.commit()
        return senhas, pessoa is not None
    finally:
        conexao.close()


def remover_contas():
    conexao = db.conectar()
    try:
        conexao.execute("DELETE FROM usuario WHERE login IN (?,?)",
                        (LOGIN_ADMIN, LOGIN_JOGADOR))
        conexao.commit()
    finally:
        conexao.close()


def sessao():
    return urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
    )


def abrir(nav, rota):
    try:
        with nav.open(BASE + rota, timeout=40) as r:
            return r.geturl(), r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as erro:
        return f"HTTP {erro.code}", ""


def entrar(nav, login, senha):
    dados = urllib.parse.urlencode({"login": login, "senha": senha}).encode()
    pedido = urllib.request.Request(BASE + "/entrar", data=dados, method="POST")
    with nav.open(pedido, timeout=40) as r:
        return r.geturl(), r.read().decode("utf-8", "replace")


def so_texto(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


PROTEGIDAS = [
    "/", "/pessoas", "/pessoas/1", "/configuracoes", "/m/futebol-masculino",
    "/m/futebol-masculino/chamada", "/m/futebol-masculino/alunos", "/minha-area",
]

DA_COORDENACAO = [
    "/pessoas", "/pessoas/1", "/pessoas/1/editar", "/pessoas/nova",
    "/configuracoes", "/m/futebol-masculino", "/m/futebol-masculino/alunos",
    "/m/futebol-masculino/chamada", "/m/futebol-masculino/matricular",
    "/m/karate/agenda", "/m/futebol-masculino/convocacao",
]

senhas, tem_pessoa = preparar_contas()

try:
    # ------------------------------------------------------------- anônimo
    print("\n1. Anonimo nao passa da porta")
    anonimo = sessao()
    for rota in PROTEGIDAS:
        url, _ = abrir(anonimo, rota)
        checar(f"{rota} manda pro login", "/entrar" in url, url)

    print("\n2. O que tem que ficar aberto sem login")
    for rota in ["/entrar", "/offline", "/sw.js", "/manifest.webmanifest"]:
        url, _ = abrir(anonimo, rota)
        checar(f"{rota} responde", "HTTP 4" not in url and "HTTP 5" not in url, url)

    # -------------------------------------------------------------- senhas
    print("\n3. Senha errada e login inexistente dao a MESMA resposta")
    _, corpo_errado = entrar(sessao(), LOGIN_ADMIN, "senha-errada-de-proposito")
    _, corpo_inexistente = entrar(sessao(), "nao-existe-esse-login-aqui", "qualquer1234")
    texto_errado = so_texto(corpo_errado)
    checar("mensagem generica", "Login ou senha não conferem" in texto_errado)
    checar("nao revela que o login existe",
           "não existe" not in texto_errado.casefold())
    checar("as duas respostas sao iguais",
           ("Login ou senha não conferem" in so_texto(corpo_inexistente))
           and ("Login ou senha não conferem" in texto_errado))

    # ------------------------------------------------------------- jogador
    print("\n4. Jogador entra e ve a area dele")
    jog = sessao()
    url, corpo = entrar(jog, LOGIN_JOGADOR, senhas[LOGIN_JOGADOR])
    checar("cai na area do jogador", "/minha-area" in url, url)
    if tem_pessoa:
        checar("a area cumprimenta pelo nome", "Olá," in so_texto(corpo))

    print("\n5. Jogador e barrado no que e da coordenacao")
    for rota in DA_COORDENACAO:
        url, _ = abrir(jog, rota)
        checar(f"{rota} barrada", "/minha-area" in url, f"chegou em {url}")

    print("\n6. O painel nao vaza telefone nem risco pro jogador")
    _, corpo = abrir(jog, "/m/futebol-masculino")
    texto = so_texto(corpo)
    checar("sem 'Ligar esta semana'", "Ligar esta semana" not in texto)
    checar("sem rotulo 'Risco de evasao'", "Risco de evasão" not in texto)
    checar("sem telefone no corpo",
           not re.search(r"\(\d\d\)\s?9\d{4}-\d{4}", texto))

    # --------------------------------------------------------------- admin
    print("\n7. Admin abre tudo")
    adm = sessao()
    entrar(adm, LOGIN_ADMIN, senhas[LOGIN_ADMIN])
    for rota in PROTEGIDAS:
        url, _ = abrir(adm, rota)
        checar(f"{rota} abre", "/entrar" not in url and "HTTP" not in url, url)

    print("\n8. Sair encerra a sessao")
    pedido = urllib.request.Request(BASE + "/sair", data=b"", method="POST")
    with adm.open(pedido, timeout=40) as r:
        r.read()
    url, _ = abrir(adm, "/pessoas")
    checar("depois de sair, /pessoas volta pro login", "/entrar" in url, url)
finally:
    remover_contas()

print("\n" + "=" * 56)
if falhas:
    print(f"{len(falhas)} verificacao(oes) de acesso falharam:")
    for f in falhas:
        print(f"  - {f}")
else:
    print("Todas as verificacoes de acesso passaram.")
sys.exit(1 if falhas else 0)
