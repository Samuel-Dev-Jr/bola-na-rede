"""
Testa a escalação: escalar, substituir, tirar, e as travas.

O que ele garante, e cada item veio de uma coisa que podia dar errado:

  - substituir manda o antigo pro BANCO, não desconvoca ele
  - ninguém em duas posições, e nenhuma posição com duas pessoas
  - posição inventada e pessoa de outra modalidade são recusadas
  - mexer na lista de convocados NÃO apaga o time já montado
  - limpar a escalação não desconvoca ninguém

Precisa do sistema rodando e de um evento com elegíveis suficientes — o
preparar_deploy.py cria três.
"""

import http.cookiejar
import re
import sqlite3
import sys
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import _acesso  # noqa: E402
import db  # noqa: E402

BASE = "http://127.0.0.1:5000"
# Caminho relativo ao módulo, e não cravado em C:\ — assim o teste roda em
# qualquer máquina, inclusive no Linux da hospedagem.
BANCO = str(db.CAMINHO_BANCO)

falhas = []


def checar(rotulo, condicao, detalhe=""):
    print(f"  [{'OK  ' if condicao else 'FALHA'}] {rotulo}"
          + (f" -- {detalhe}" if detalhe and not condicao else ""))
    if not condicao:
        falhas.append(rotulo)


nav = urllib.request.build_opener(
    urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
)


def postar(rota, campos):
    # doseq=True: sem isso uma lista virava UMA string com colchetes, o formulário
    # chegava com um valor só e a rota estourava 500 tentando int() nele.
    dados = urllib.parse.urlencode(campos, doseq=True).encode()
    p = urllib.request.Request(BASE + rota, data=dados, method="POST")
    with nav.open(p, timeout=60) as r:
        return r.geturl(), r.read().decode("utf-8", "replace")


def abrir(rota):
    with nav.open(BASE + rota, timeout=60) as r:
        return r.read().decode("utf-8", "replace")


def texto(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


# Conta de teste com senha aleatória, criada e apagada por este script — em vez
# de depender de uma senha fixa que só existe na minha máquina.
senha_teste = _acesso.preparar_admin()
_, corpo_login = postar("/entrar", {"login": _acesso.LOGIN_TESTE,
                                    "senha": senha_teste})
if "Login ou senha" in corpo_login:
    _acesso.remover_admin()
    raise SystemExit("não consegui entrar; o teste seria feito na tela de login")

con = sqlite3.connect(BANCO)
con.row_factory = sqlite3.Row

# Procuro um evento de futebol que tenha pelo menos 6 elegíveis. A elegibilidade
# segue a MESMA regra da rota: evento de turma só aceita quem é daquela turma;
# evento da modalidade aceita qualquer um dela. Espelhar essa regra aqui é o que
# evita o teste falhar por motivo errado, escalando alguém que a rota recusa.
evento = None
for candidato in con.execute(
    """SELECT e.id, e.turma_id, e.modalidade_id, m.slug FROM evento e
       JOIN modalidade m ON m.id = e.modalidade_id
       WHERE m.slug LIKE 'futebol%' ORDER BY e.id"""
):
    if candidato["turma_id"]:
        lista = [r["id"] for r in con.execute(
            "SELECT id FROM matricula WHERE turma_id = ?", (candidato["turma_id"],))]
    else:
        lista = [r["id"] for r in con.execute(
            """SELECT ma.id FROM matricula ma JOIN turma t ON t.id = ma.turma_id
               WHERE t.modalidade_id = ?""", (candidato["modalidade_id"],))]
    if len(lista) >= 6:
        evento, elegiveis = candidato, lista[:6]
        break

if evento is None:
    print("  Nenhum evento de futebol com 6+ elegíveis. O teste precisa de 6 pra "
          "exercitar substituição e disputa de posição.")
    sys.exit(2)

ev = evento["id"]
print(f"\n  evento {ev} ({evento['slug']}), "
      f"{'turma ' + str(evento['turma_id']) if evento['turma_id'] else 'modalidade inteira'}, "
      f"{len(elegiveis)} elegíveis usados")

print("\n1. O campo aparece na tela")
html = abrir(f"/convocacao/{ev}")
checar("tem o desenho do campo", 'class="quadra' in html)
checar("tem as 11 posições do futebol", html.count('class="posicao') >= 11,
       f"{html.count('class=\"posicao')}")

print("\n2. Escalar alguém no gol")
postar(f"/convocacao/{ev}/escalar",
       {"matricula_id": elegiveis[0], "posicao": "GOL"})
linha = con.execute(
    "SELECT posicao FROM convocacao WHERE evento_id = ? AND matricula_id = ?",
    (ev, elegiveis[0])).fetchone()
checar("gravou a posição", linha and linha["posicao"] == "GOL",
       linha["posicao"] if linha else "sem linha")

print("\n3. Substituir: o antigo vai pro banco, não some")
postar(f"/convocacao/{ev}/escalar",
       {"matricula_id": elegiveis[1], "posicao": "GOL"})
antigo = con.execute(
    "SELECT posicao FROM convocacao WHERE evento_id = ? AND matricula_id = ?",
    (ev, elegiveis[0])).fetchone()
novo = con.execute(
    "SELECT posicao FROM convocacao WHERE evento_id = ? AND matricula_id = ?",
    (ev, elegiveis[1])).fetchone()
checar("o novo assumiu o gol", novo and novo["posicao"] == "GOL")
checar("o antigo continua convocado", antigo is not None)
checar("e foi pro banco (posição nula)", antigo and antigo["posicao"] is None,
       antigo["posicao"] if antigo else "-")

print("\n4. Ninguém em dois lugares ao mesmo tempo")
postar(f"/convocacao/{ev}/escalar",
       {"matricula_id": elegiveis[1], "posicao": "ATA-D"})
posicoes = [r["posicao"] for r in con.execute(
    "SELECT posicao FROM convocacao WHERE evento_id = ? AND matricula_id = ?",
    (ev, elegiveis[1]))]
checar("ele mudou de posição, não duplicou", posicoes == ["ATA-D"], str(posicoes))

print("\n5. Duas pessoas na mesma posição, nunca")
postar(f"/convocacao/{ev}/escalar", {"matricula_id": elegiveis[2], "posicao": "VOL"})
postar(f"/convocacao/{ev}/escalar", {"matricula_id": elegiveis[3], "posicao": "VOL"})
no_vol = [r["matricula_id"] for r in con.execute(
    "SELECT matricula_id FROM convocacao WHERE evento_id = ? AND posicao = 'VOL'", (ev,))]
checar("só um volante", len(no_vol) == 1, f"{len(no_vol)} pessoas")

print("\n6. Posição inventada é recusada")
_, corpo = postar(f"/convocacao/{ev}/escalar",
                  {"matricula_id": elegiveis[4], "posicao": "GOLEIRAO"})
checar("recusa código desconhecido", "Posição desconhecida" in texto(corpo),
       texto(corpo)[:120])
gravou = con.execute(
    "SELECT 1 FROM convocacao WHERE evento_id = ? AND posicao = 'GOLEIRAO'",
    (ev,)).fetchone()
checar("e não gravou nada", gravou is None)

print("\n7. Escalar alguém de outra modalidade é recusado")
de_fora = con.execute(
    """SELECT ma.id FROM matricula ma JOIN turma t ON t.id = ma.turma_id
       JOIN modalidade m ON m.id = t.modalidade_id
       WHERE m.slug = 'karate' LIMIT 1""").fetchone()
_, corpo = postar(f"/convocacao/{ev}/escalar",
                  {"matricula_id": de_fora["id"], "posicao": "MEI-C"})
checar("recusa quem não é elegível", "não está entre os elegíveis" in texto(corpo),
       texto(corpo)[:120])

print("\n8. Mexer nos convocados NÃO apaga a escalação")
antes = {r["matricula_id"]: r["posicao"] for r in con.execute(
    "SELECT matricula_id, posicao FROM convocacao WHERE evento_id = ?", (ev,))}
escalados_antes = {k: v for k, v in antes.items() if v}
todos = list(antes) + [elegiveis[5]]
postar(f"/convocacao/{ev}", {"convocado": [str(i) for i in todos]})
depois = {r["matricula_id"]: r["posicao"] for r in con.execute(
    "SELECT matricula_id, posicao FROM convocacao WHERE evento_id = ?", (ev,))}
escalados_depois = {k: v for k, v in depois.items() if v}
checar("a escalação sobreviveu", escalados_antes == escalados_depois,
       f"{len(escalados_antes)} -> {len(escalados_depois)}")

print("\n9. A mensagem do WhatsApp sai na ordem do campo")
html = abrir(f"/convocacao/{ev}")
msg = re.search(r'id="mensagem">(.*?)</pre>', html, re.S)
if msg:
    corpo_msg = msg.group(1)
    checar("tem seção de escalação", "Escala" in corpo_msg)
    checar("cita posição por extenso", "Goleiro" in corpo_msg or "Volante" in corpo_msg,
           corpo_msg[:200])
    checar("tem banco", "banco" in corpo_msg.casefold())
else:
    checar("achou a mensagem", False)

print("\n10. Limpar escalação não desconvoca ninguém")
antes_qtd = con.execute(
    "SELECT COUNT(*) c FROM convocacao WHERE evento_id = ?", (ev,)).fetchone()["c"]
postar(f"/convocacao/{ev}/limpar-escalacao", {})
depois_qtd = con.execute(
    "SELECT COUNT(*) c FROM convocacao WHERE evento_id = ?", (ev,)).fetchone()["c"]
com_posicao = con.execute(
    "SELECT COUNT(*) c FROM convocacao WHERE evento_id = ? AND posicao IS NOT NULL",
    (ev,)).fetchone()["c"]
checar("todo mundo continua convocado", antes_qtd == depois_qtd,
       f"{antes_qtd} -> {depois_qtd}")
checar("e ninguém mais está em campo", com_posicao == 0, f"{com_posicao}")

con.close()
_acesso.remover_admin()

print("\n" + "=" * 56)
if falhas:
    print(f"{len(falhas)} falha(s):")
    for f in falhas:
        print(f"  - {f}")
else:
    print("Escalacao passou em tudo.")
sys.exit(1 if falhas else 0)
