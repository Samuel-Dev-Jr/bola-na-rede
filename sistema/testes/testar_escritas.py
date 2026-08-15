"""Exercita as rotas de escrita do modelo pessoa/matrícula."""

import http.cookiejar
import sqlite3
import sys
import urllib.parse
import urllib.request

import _acesso
import db

BASE = "http://127.0.0.1:5000"

# O caminho do banco estava escrito à mão aqui, apontando pra C:\PROJETOS — a
# pasta do MEU computador. Em qualquer outra máquina o sqlite3 não reclamava:
# ele CRIA um arquivo vazio com esse nome e o teste morria em "no such table:
# turma", como se o banco estivesse quebrado. Erro que mente sobre a causa é
# pior que erro nenhum. Agora vem do db.py, que é quem sabe onde o banco fica —
# o mesmo caminho que o sistema usa, em qualquer sistema operacional.
BANCO = db.CAMINHO_BANCO

falhas = []

# Desde que o sistema passou a exigir login, gravar exige sessão: sem cookie
# todo POST cai na tela de entrar e o teste passaria sem gravar nada.
navegador = urllib.request.build_opener(
    urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
)


def postar(caminho, campos):
    dados = urllib.parse.urlencode(campos, doseq=True).encode()
    req = urllib.request.Request(BASE + caminho, data=dados, method="POST")
    with navegador.open(req, timeout=40) as r:
        return r.status, r.read().decode("utf-8", "replace")


def entrar_como_admin():
    senha = _acesso.preparar_admin()
    _, corpo = postar("/entrar", {"login": _acesso.LOGIN_TESTE, "senha": senha})
    # Se o login falhar, todo o resto do teste mede a tela de entrar e "passa"
    # sem testar nada. Melhor parar aqui, alto e claro.
    if "Login ou senha" in corpo:
        raise RuntimeError("não consegui entrar como admin; o teste seria inútil")


entrar_como_admin()


def checar(rotulo, condicao, detalhe=""):
    print(f"  [{'OK  ' if condicao else 'FALHA'}] {rotulo}"
          + (f" -- {detalhe}" if detalhe and not condicao else ""))
    if not condicao:
        falhas.append(rotulo)


con = sqlite3.connect(BANCO)
con.row_factory = sqlite3.Row
# O SQLite desliga chave estrangeira por padrao EM CADA CONEXAO. Sem esta
# linha o teste de CASCADE dava falso negativo: o DELETE passava e as
# matriculas ficavam orfas so no meu script, nao no sistema.
con.execute("PRAGMA foreign_keys = ON")

# ------------------------------------------------------------------ chamada
print("\n1. POST /m/<slug>/chamada")
for slug, dia in [("karate", "2026-08-12"), ("volei-feminino", "2026-08-12")]:
    turma = con.execute(
        """SELECT t.id FROM turma t JOIN modalidade m ON m.id = t.modalidade_id
           WHERE m.slug = ? ORDER BY t.ordem LIMIT 1""", (slug,)).fetchone()
    mats = [r["id"] for r in con.execute(
        "SELECT id FROM matricula WHERE turma_id = ? LIMIT 3", (turma["id"],))]
    if not mats:
        continue

    campos = {"data": dia, "turma_id": turma["id"]}
    for i, mid in enumerate(mats):
        campos[f"matricula_{mid}"] = ["presente", "falta", "justificada"][i % 3]

    status, _ = postar(f"/m/{slug}/chamada", campos)
    checar(f"{slug}: responde 200", status == 200, f"status={status}")
    gravados = {r["matricula_id"]: r["status"] for r in con.execute(
        "SELECT matricula_id, status FROM presenca WHERE data = ?", (dia,))}
    esperado = [["presente", "falta", "justificada"][i % 3] for i in range(len(mats))]
    checar(f"{slug}: gravou os estados",
           [gravados.get(m) for m in mats] == esperado,
           str([gravados.get(m) for m in mats]))

    postar(f"/m/{slug}/chamada", campos)
    n = con.execute("SELECT COUNT(*) c FROM presenca WHERE data=? AND matricula_id=?",
                    (dia, mats[0])).fetchone()["c"]
    checar(f"{slug}: regravar nao duplica", n == 1, f"{n} linhas")

# ------------------------------------------------------- cadastro de pessoa
print("\n2. POST /m/karate/pessoas/nova  (cadastra e ja matricula)")
turma_karate = con.execute(
    """SELECT t.id FROM turma t JOIN modalidade m ON m.id = t.modalidade_id
       WHERE m.slug = 'karate' ORDER BY t.ordem LIMIT 1""").fetchone()

status, _ = postar("/m/karate/pessoas/nova", {
    "nome": "Teste Automatizado da Silva",
    "data_nascimento": "2014-03-15",
    "turma_id": turma_karate["id"],
    "responsavel_nome": "Responsavel de Teste",
    "responsavel_parentesco": "Mãe",
    "responsavel_telefone": "(11) 91234-5678",
    "condicoes": "Asma",
    "autoriza_imagem": "1",
})
checar("responde 200", status == 200, f"status={status}")

nova = con.execute(
    "SELECT * FROM pessoa WHERE nome = 'Teste Automatizado da Silva'").fetchone()
checar("pessoa criada", nova is not None)

if nova:
    mats = con.execute(
        "SELECT * FROM matricula WHERE pessoa_id = ?", (nova["id"],)).fetchall()
    checar("ja nasceu com 1 matricula", len(mats) == 1, f"{len(mats)}")
    checar("ficha medica salva", nova["condicoes"] == "Asma", str(nova["condicoes"]))

    # -------------------------------------------------- segunda modalidade
    print("\n3. POST /m/futebol-masculino/matricular  (mesma pessoa, 2a atividade)")
    turma_fut = con.execute(
        """SELECT t.id FROM turma t JOIN modalidade m ON m.id = t.modalidade_id
           WHERE m.slug = 'futebol-masculino' ORDER BY t.ordem LIMIT 1""").fetchone()
    status, _ = postar("/m/futebol-masculino/matricular", {
        "pessoa_id": nova["id"], "turma_id": turma_fut["id"],
        "data_matricula": "2026-08-10",
    })
    checar("responde 200", status == 200, f"status={status}")
    mats = con.execute(
        "SELECT * FROM matricula WHERE pessoa_id = ?", (nova["id"],)).fetchall()
    checar("agora tem 2 matriculas", len(mats) == 2, f"{len(mats)}")
    pessoas_iguais = con.execute(
        "SELECT COUNT(*) c FROM pessoa WHERE nome = 'Teste Automatizado da Silva'"
    ).fetchone()["c"]
    checar("NAO duplicou a pessoa", pessoas_iguais == 1, f"{pessoas_iguais} linhas")

    # ------------------------------------------------- matricula repetida
    print("\n4. POST matricular de novo na MESMA turma (deve recusar)")
    postar("/m/futebol-masculino/matricular", {
        "pessoa_id": nova["id"], "turma_id": turma_fut["id"],
    })
    mats = con.execute(
        "SELECT * FROM matricula WHERE pessoa_id = ?", (nova["id"],)).fetchall()
    checar("continua com 2, nao 3", len(mats) == 2, f"{len(mats)}")

    # ---------------------------------------------------- encerrar/reabrir
    print("\n5. POST /matriculas/<id>/encerrar")
    alvo = mats[0]["id"]
    postar(f"/matriculas/{alvo}/encerrar", {})
    st = con.execute("SELECT status FROM matricula WHERE id = ?", (alvo,)).fetchone()["status"]
    checar("encerrou", st == "encerrada", st)
    postar(f"/matriculas/{alvo}/encerrar", {})
    st = con.execute("SELECT status FROM matricula WHERE id = ?", (alvo,)).fetchone()["status"]
    checar("reabriu", st == "ativa", st)

    # --------------------------------------------------------- editar ficha
    print("\n6. POST /pessoas/<id>/editar")
    status, _ = postar(f"/pessoas/{nova['id']}/editar", {
        "nome": "Teste Editado da Silva",
        "data_nascimento": "2014-03-15",
        "responsavel_nome": "Responsavel Editado",
        "responsavel_parentesco": "Pai",
        "responsavel_telefone": "(11) 90000-1111",
    })
    checar("responde 200", status == 200, f"status={status}")
    editada = con.execute("SELECT * FROM pessoa WHERE id = ?", (nova["id"],)).fetchone()
    checar("nome atualizado", editada["nome"] == "Teste Editado da Silva", editada["nome"])
    checar("campo limpo vira NULL", editada["condicoes"] is None, str(editada["condicoes"]))
    mats_depois = con.execute(
        "SELECT COUNT(*) c FROM matricula WHERE pessoa_id = ?", (nova["id"],)).fetchone()["c"]
    checar("editar nao mexeu nas matriculas", mats_depois == 2, f"{mats_depois}")

    con.execute("DELETE FROM pessoa WHERE id = ?", (nova["id"],))
    con.commit()
    sobrou = con.execute(
        "SELECT COUNT(*) c FROM matricula WHERE pessoa_id = ?", (nova["id"],)).fetchone()["c"]
    checar("apagar pessoa levou as matriculas junto (CASCADE)", sobrou == 0, f"{sobrou}")

# --------------------------------------------------------------- convocação
print("\n7. POST /convocacao/<id>")
evento = con.execute(
    """SELECT e.id, e.turma_id FROM evento e
       JOIN modalidade m ON m.id = e.modalidade_id
       WHERE m.slug = 'futebol-masculino' LIMIT 1""").fetchone()

# Sem evento no banco isto quebrava com "NoneType object is not subscriptable",
# e o traceback não dizia o que faltava. Agora falha explicando.
if evento is None:
    checar("existe evento pra testar convocação", False,
           "nenhum evento no banco — crie um pela tela, "
           "ou rode preparar_deploy.py, que já cria alguns")
else:
    elegiveis = [r["id"] for r in con.execute(
        "SELECT id FROM matricula WHERE turma_id = ? LIMIT 4",
        (evento["turma_id"],))]
    status, _ = postar(f"/convocacao/{evento['id']}",
                       {"convocado": [str(i) for i in elegiveis]})
    checar("responde 200", status == 200, f"status={status}")
    convocados = [r["matricula_id"] for r in con.execute(
        "SELECT matricula_id FROM convocacao WHERE evento_id = ?", (evento["id"],))]
    checar("substitui a lista", sorted(convocados) == sorted(elegiveis),
           f"{len(convocados)}")

con.close()
_acesso.remover_admin()

print("\n" + "=" * 56)
if falhas:
    print(f"{len(falhas)} FALHA(S): " + ", ".join(falhas))
    sys.exit(1)
print("Todas as rotas de escrita passaram.")
