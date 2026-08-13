"""
Consultas que leem o banco.

Separei isso das rotas porque no começo eu tinha deixado tudo dentro do app.py
e virou uma bagunça pra achar qualquer coisa. Aqui só leio e calculo; quem
grava é o app.py.

Dois detalhes que mudam tudo por aqui:

1. Uma PESSOA pode ter várias MATRÍCULAS. Quase toda função abaixo trabalha
   com matrícula, não com pessoa, porque frequência e evasão são por
   modalidade. A tela da pessoa é o único lugar que junta tudo de novo.

2. Cada modalidade tem dias de aula diferentes, então a tirinha de presença de
   quem faz karatê é montada contra o calendário do karatê. Se eu usasse um
   calendário só, quem joga vôlei apareceria faltando na terça, dia em que o
   vôlei nem abre.
"""

import os
import sqlite3
from datetime import date, timedelta
from typing import Optional

from risco import (
    PRIORIDADE_RISCO,
    AvaliacaoRisco,
    RegistroPresenca,
    avaliar_risco,
)

MESES_PT = {
    1: "jan", 2: "fev", 3: "mar", 4: "abr", 5: "mai", 6: "jun",
    7: "jul", 8: "ago", 9: "set", 10: "out", 11: "nov", 12: "dez",
}

MESES_NOME = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril", 5: "Maio",
    6: "Junho", 7: "Julho", 8: "Agosto", 9: "Setembro", 10: "Outubro",
    11: "Novembro", 12: "Dezembro",
}

DIAS_SEMANA_CURTO = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]

# Antes eu tinha deixado a data fixa aqui, pra os números do relatório não
# mudarem depois da entrega. O problema é que isso congela o sistema: a janela de
# 30 dias e o cálculo de evasão param no tempo, e quem abrisse o sistema um mês
# depois veria a situação de um mês atrás como se fosse a de hoje.
#
# Agora a data é a de verdade, e ela é lida a cada chamada de hoje() — não pode
# ser constante de módulo, senão congela enquanto o servidor estiver de pé.
#
# A variável de ambiente existe pra uma coisa só: travar a data na hora de tirar
# os prints ou gravar o vídeo, pra a tela não mudar entre uma captura e outra.
#     Windows:  set BOLA_NA_REDE_HOJE=2026-08-12
VARIAVEL_DATA_FIXA = "BOLA_NA_REDE_HOJE"

# 12 aulas dá mais ou menos um mês. Testei com 8 e com 20: 8 era pouco pra dar
# pra perceber a queda, 20 não cabia na tabela.
MARCAS_VISIVEIS = 12


def hoje() -> date:
    fixada = os.environ.get(VARIAVEL_DATA_FIXA)
    return date.fromisoformat(fixada) if fixada else date.today()


def idade(nascimento: date) -> int:
    referencia = hoje()
    anos = referencia.year - nascimento.year
    if (referencia.month, referencia.day) < (nascimento.month, nascimento.day):
        anos -= 1
    return anos


# ------------------------------------------------------------ modalidades


def _com_nome_exibicao(linha: sqlite3.Row) -> dict:
    """
    Monta o nome que aparece na tela.

    Guardo nome e gênero separados no banco porque preciso agrupar por esporte
    em alguns lugares. Mas na tela o usuário quer ler "Futebol Feminino" de
    uma vez, e nas turmas mistas o gênero não deve aparecer.
    """
    modalidade = dict(linha)
    modalidade["nome_exibicao"] = (
        modalidade["nome"] if modalidade["genero"] == "Misto"
        else f"{modalidade['nome']} {modalidade['genero']}"
    )
    return modalidade


def listar_modalidades(conexao: sqlite3.Connection) -> list[dict]:
    return [_com_nome_exibicao(l)
            for l in conexao.execute("SELECT * FROM modalidade ORDER BY ordem")]


def obter_modalidade(conexao: sqlite3.Connection, slug: str) -> Optional[dict]:
    linha = conexao.execute("SELECT * FROM modalidade WHERE slug = ?", (slug,)).fetchone()
    return _com_nome_exibicao(linha) if linha else None


def turmas_da_modalidade(conexao: sqlite3.Connection, modalidade_id: int) -> list[dict]:
    return [dict(l) for l in conexao.execute(
        "SELECT * FROM turma WHERE modalidade_id = ? ORDER BY ordem", (modalidade_id,))]


def datas_de_aula(conexao: sqlite3.Connection, modalidade_id: int,
                  limite: int = MARCAS_VISIVEIS) -> list[date]:
    """As últimas datas em que essa modalidade teve aula, da mais antiga à mais nova."""
    linhas = conexao.execute(
        """
        SELECT DISTINCT p.data
        FROM presenca p
        JOIN matricula ma ON ma.id = p.matricula_id
        JOIN turma t ON t.id = ma.turma_id
        WHERE t.modalidade_id = ? AND p.data <= ?
        ORDER BY p.data DESC LIMIT ?
        """,
        (modalidade_id, hoje(), limite),
    ).fetchall()
    return sorted(l["data"] for l in linhas)


def proxima_data_de_aula(dias_aula: str) -> date:
    dias = {int(d) for d in dias_aula.split(",")}
    referencia = hoje()
    dia = referencia
    for _ in range(14):
        if dia.weekday() in dias:
            return dia
        dia += timedelta(days=1)
    return referencia


# ------------------------------------------------------------------ risco


def _presencas_por_matricula(
    conexao: sqlite3.Connection, modalidade_id: Optional[int] = None
) -> dict[int, list[RegistroPresenca]]:
    sql = """
        SELECT p.matricula_id, p.data, p.status
        FROM presenca p
        JOIN matricula ma ON ma.id = p.matricula_id
        JOIN turma t ON t.id = ma.turma_id
    """
    parametros: list = []
    if modalidade_id is not None:
        sql += " WHERE t.modalidade_id = ?"
        parametros.append(modalidade_id)

    agrupado: dict[int, list[RegistroPresenca]] = {}
    for linha in conexao.execute(sql, parametros):
        agrupado.setdefault(linha["matricula_id"], []).append(
            RegistroPresenca(linha["data"], linha["status"])
        )
    return agrupado


def _montar_marcas(registros: list[RegistroPresenca], datas: list[date]) -> list[str]:
    """
    Monta a tirinha de quadradinhos que aparece nas tabelas.

    Aqui eu errei na primeira versão e demorei pra perceber: eu montava a tira
    pegando os últimos registros do próprio aluno. Só que quem evadiu não tem
    registro nenhum nas aulas recentes, então a tira mostrava o período em que
    ele ainda vinha, quase toda verde, bem do lado do selo "Evadido".

    Agora eu percorro as datas de aula da modalidade e, quando não tem registro
    naquele dia, marco como "sem_registro".
    """
    por_data = {r.data: r.status for r in registros}
    return [por_data.get(dia, "sem_registro") for dia in datas]


def avaliacoes_e_marcas(
    conexao: sqlite3.Connection, modalidade_id: Optional[int] = None
) -> dict[int, tuple[AvaliacaoRisco, list[str]]]:
    """Risco e tirinha de cada MATRÍCULA, indexados pelo id da matrícula."""
    agrupado = _presencas_por_matricula(conexao, modalidade_id)

    sql = """
        SELECT ma.id, t.modalidade_id
        FROM matricula ma JOIN turma t ON t.id = ma.turma_id
    """
    parametros: list = []
    if modalidade_id is not None:
        sql += " WHERE t.modalidade_id = ?"
        parametros.append(modalidade_id)
    matriculas = conexao.execute(sql, parametros).fetchall()

    # Cada modalidade tem o seu calendário; busco uma vez e reaproveito.
    calendarios: dict[int, list[date]] = {}
    for m in matriculas:
        if m["modalidade_id"] not in calendarios:
            calendarios[m["modalidade_id"]] = datas_de_aula(conexao, m["modalidade_id"])

    # Uma referência só pro lote inteiro. Se eu chamasse hoje() dentro do laço,
    # um lote que atravessasse a meia-noite classificaria as primeiras matrículas
    # contra um dia e as últimas contra outro.
    referencia = hoje()

    resultado = {}
    for m in matriculas:
        registros = sorted(agrupado.get(m["id"], []), key=lambda r: r.data)
        resultado[m["id"]] = (
            avaliar_risco(registros, referencia),
            _montar_marcas(registros, calendarios[m["modalidade_id"]]),
        )
    return resultado


# -------------------------------------------------------------- matrículas


CAMPOS_MATRICULA = """
    ma.id            AS matricula_id,
    ma.status        AS matricula_status,
    ma.data_matricula,
    ma.numero,
    p.id             AS pessoa_id,
    p.nome, p.data_nascimento, p.responsavel_nome, p.responsavel_parentesco,
    p.responsavel_telefone, p.emergencia_nome, p.emergencia_telefone,
    p.alergias, p.condicoes, p.medicacao_continua, p.plano_saude,
    p.observacoes_medicas, p.autoriza_imagem,
    t.id             AS turma_id,
    t.nome           AS turma_nome,
    m.id             AS modalidade_id,
    m.slug           AS modalidade_slug,
    m.nome           AS modalidade_nome,
    m.genero         AS modalidade_genero,
    m.cor            AS modalidade_cor,
    m.horario        AS modalidade_horario,
    m.dias_aula      AS modalidade_dias_aula
"""

JUNCAO_MATRICULA = """
    FROM matricula ma
    JOIN pessoa p     ON p.id = ma.pessoa_id
    JOIN turma t      ON t.id = ma.turma_id
    JOIN modalidade m ON m.id = t.modalidade_id
"""


def outras_atividades(conexao: sqlite3.Connection) -> dict[int, list[dict]]:
    """
    Para cada pessoa, a lista de modalidades em que ela está.

    Uso isso pra mostrar "também faz Basquete" na listagem. Foi o que mais
    mudou a cara do sistema depois que separei pessoa de matrícula: dá pra ver
    de relance quem está espalhado por várias atividades.
    """
    agrupado: dict[int, list[dict]] = {}
    for linha in conexao.execute(
        f"""
        SELECT ma.pessoa_id, ma.id AS matricula_id, m.slug, m.nome, m.genero, m.cor
        {JUNCAO_MATRICULA}
        ORDER BY m.ordem
        """
    ):
        agrupado.setdefault(linha["pessoa_id"], []).append({
            "matricula_id": linha["matricula_id"],
            "slug": linha["slug"],
            "cor": linha["cor"],
            "nome_exibicao": (linha["nome"] if linha["genero"] == "Misto"
                              else f"{linha['nome']} {linha['genero']}"),
        })
    return agrupado


def listar_matriculas(
    conexao: sqlite3.Connection,
    modalidade_id: Optional[int] = None,
    busca: str = "",
    turma_id: str = "",
    nivel: str = "",
) -> list[dict]:
    sql = f"SELECT {CAMPOS_MATRICULA} {JUNCAO_MATRICULA} WHERE 1=1"
    parametros: list = []

    if modalidade_id is not None:
        sql += " AND m.id = ?"
        parametros.append(modalidade_id)
    if busca:
        sql += " AND (p.nome LIKE ? OR p.responsavel_nome LIKE ?)"
        parametros += [f"%{busca}%", f"%{busca}%"]
    if turma_id:
        sql += " AND ma.turma_id = ?"
        parametros.append(turma_id)

    sql += " ORDER BY p.nome"

    # O filtro por nível é feito em Python e não no SQL, porque o risco não
    # está gravado no banco, é calculado na hora.
    mapa = avaliacoes_e_marcas(conexao, modalidade_id)
    todas = outras_atividades(conexao)

    resultado = []
    for linha in conexao.execute(sql, parametros):
        avaliacao, marcas = mapa[linha["matricula_id"]]
        if nivel and avaliacao.nivel != nivel:
            continue
        item = dict(linha)
        item["avaliacao"] = avaliacao
        item["marcas"] = marcas
        item["idade"] = idade(linha["data_nascimento"])
        item["outras"] = [
            a for a in todas.get(linha["pessoa_id"], [])
            if a["matricula_id"] != linha["matricula_id"]
        ]
        resultado.append(item)

    resultado.sort(key=lambda a: (PRIORIDADE_RISCO[a["avaliacao"].nivel], a["nome"]))
    return resultado


def obter_matricula(conexao: sqlite3.Connection, matricula_id: int) -> Optional[dict]:
    linha = conexao.execute(
        f"SELECT {CAMPOS_MATRICULA} {JUNCAO_MATRICULA} WHERE ma.id = ?", (matricula_id,)
    ).fetchone()
    return dict(linha) if linha else None


# ------------------------------------------------------------------ pessoa


def obter_pessoa(conexao: sqlite3.Connection, pessoa_id: int) -> Optional[dict]:
    """
    A ficha da pessoa, com TODAS as matrículas dela.

    É a tela que só passou a existir depois de separar pessoa de matrícula.
    Antes, pra saber que o Samuel também jogava basquete, era preciso procurar
    na outra lista — e era comum a ficha médica estar preenchida só em uma.
    """
    pessoa = conexao.execute("SELECT * FROM pessoa WHERE id = ?", (pessoa_id,)).fetchone()
    if pessoa is None:
        return None

    mapa = avaliacoes_e_marcas(conexao)
    matriculas = []
    for linha in conexao.execute(
        f"""
        SELECT {CAMPOS_MATRICULA} {JUNCAO_MATRICULA}
        WHERE ma.pessoa_id = ? ORDER BY m.ordem
        """,
        (pessoa_id,),
    ):
        avaliacao, marcas = mapa[linha["matricula_id"]]
        registros = [
            RegistroPresenca(r["data"], r["status"])
            for r in conexao.execute(
                "SELECT data, status FROM presenca WHERE matricula_id = ? ORDER BY data",
                (linha["matricula_id"],),
            )
        ]
        matriculas.append({
            **dict(linha),
            "avaliacao": avaliacao,
            "marcas": marcas,
            "nome_exibicao": (
                linha["modalidade_nome"] if linha["modalidade_genero"] == "Misto"
                else f"{linha['modalidade_nome']} {linha['modalidade_genero']}"
            ),
            "total_presencas": sum(1 for r in registros if r.status == "presente"),
            "total_aulas": len(registros),
            "ultimas_presencas": list(reversed(registros[-MARCAS_VISIVEIS:])),
        })

    return {
        **dict(pessoa),
        "idade": idade(pessoa["data_nascimento"]),
        "matriculas": matriculas,
        # O pior nível entre as matrículas: é o que decide o alerta no topo.
        "pior_nivel": min(
            (m["avaliacao"].nivel for m in matriculas),
            key=lambda n: PRIORIDADE_RISCO[n], default="regular",
        ),
    }


def listar_pessoas(conexao: sqlite3.Connection, busca: str = "") -> list[dict]:
    """Todas as pessoas do Centro, com quantas atividades cada uma faz."""
    sql = """
        SELECT p.*, COUNT(ma.id) AS total_matriculas
        FROM pessoa p LEFT JOIN matricula ma ON ma.pessoa_id = p.id
        WHERE 1=1
    """
    parametros: list = []
    if busca:
        sql += " AND (p.nome LIKE ? OR p.responsavel_nome LIKE ?)"
        parametros += [f"%{busca}%", f"%{busca}%"]
    sql += " GROUP BY p.id ORDER BY p.nome"

    todas = outras_atividades(conexao)
    return [
        {**dict(l), "idade": idade(l["data_nascimento"]),
         "atividades": todas.get(l["id"], [])}
        for l in conexao.execute(sql, parametros)
    ]


# --------------------------------------------------------------- resumos


def resumo(conexao: sqlite3.Connection, modalidade_id: Optional[int] = None) -> dict:
    """Os números dos cartões do painel. Conta matrículas, não pessoas."""
    mapa = avaliacoes_e_marcas(conexao, modalidade_id)

    sql = """
        SELECT ma.id, ma.status, ma.pessoa_id
        FROM matricula ma JOIN turma t ON t.id = ma.turma_id
    """
    parametros: list = []
    if modalidade_id is not None:
        sql += " WHERE t.modalidade_id = ?"
        parametros.append(modalidade_id)
    matriculas = conexao.execute(sql, parametros).fetchall()

    contagem = {"regular": 0, "atencao": 0, "risco": 0, "evadido": 0}
    for m in matriculas:
        contagem[mapa[m["id"]][0].nivel] += 1

    # Matrículas que continuam ativas no papel para quem já parou de aparecer.
    fantasmas = sum(
        1 for m in matriculas
        if m["status"] == "ativa" and mapa[m["id"]][0].nivel == "evadido"
    )

    inicio = hoje() - timedelta(days=30)
    sql_freq = """
        SELECT SUM(CASE WHEN p.status = 'presente' THEN 1 ELSE 0 END) AS presentes,
               SUM(CASE WHEN p.status = 'falta'    THEN 1 ELSE 0 END) AS faltas
        FROM presenca p
        JOIN matricula ma ON ma.id = p.matricula_id
        JOIN turma t ON t.id = ma.turma_id
        WHERE p.data >= ?
    """
    parametros_freq: list = [inicio]
    if modalidade_id is not None:
        sql_freq += " AND t.modalidade_id = ?"
        parametros_freq.append(modalidade_id)

    linha = conexao.execute(sql_freq, parametros_freq).fetchone()
    base = (linha["presentes"] or 0) + (linha["faltas"] or 0)

    return {
        "matriculas": len(matriculas),
        "pessoas": len({m["pessoa_id"] for m in matriculas}),
        "ativas_no_papel": sum(1 for m in matriculas if m["status"] == "ativa"),
        "ativas_de_fato": len(matriculas) - contagem["evadido"],
        "fantasmas": fantasmas,
        "frequencia_mes": round((linha["presentes"] or 0) / base * 100) if base else 0,
        "contagem": contagem,
    }


def painel_do_centro(conexao: sqlite3.Connection) -> dict:
    """
    Tela inicial: um cartão por modalidade, mais o total do Centro.

    Calculo o risco uma vez só, para todas as matrículas, e depois separo por
    modalidade. Fazer uma consulta por modalidade seria mais fácil de ler, mas
    repetiria o cálculo oito vezes.
    """
    mapa = avaliacoes_e_marcas(conexao)
    matriculas = conexao.execute(
        """
        SELECT ma.id, ma.status, ma.pessoa_id, t.modalidade_id
        FROM matricula ma JOIN turma t ON t.id = ma.turma_id
        """
    ).fetchall()

    inicio = hoje() - timedelta(days=30)
    frequencias = {
        l["modalidade_id"]: l
        for l in conexao.execute(
            """
            SELECT t.modalidade_id,
                   SUM(CASE WHEN p.status = 'presente' THEN 1 ELSE 0 END) AS presentes,
                   SUM(CASE WHEN p.status = 'falta'    THEN 1 ELSE 0 END) AS faltas
            FROM presenca p
            JOIN matricula ma ON ma.id = p.matricula_id
            JOIN turma t ON t.id = ma.turma_id
            WHERE p.data >= ?
            GROUP BY t.modalidade_id
            """,
            (inicio,),
        )
    }

    cartoes = []
    for modalidade in listar_modalidades(conexao):
        dela = [m for m in matriculas if m["modalidade_id"] == modalidade["id"]]
        contagem = {"regular": 0, "atencao": 0, "risco": 0, "evadido": 0}
        for m in dela:
            contagem[mapa[m["id"]][0].nivel] += 1

        linha = frequencias.get(modalidade["id"])
        base = ((linha["presentes"] or 0) + (linha["faltas"] or 0)) if linha else 0

        cartoes.append({
            **modalidade,
            "matriculas": len(dela),
            "em_atividade": len(dela) - contagem["evadido"],
            "frequencia": round((linha["presentes"] or 0) / base * 100) if base else 0,
            "contagem": contagem,
            "precisam_atencao": contagem["risco"] + contagem["atencao"],
            "trazer_de_volta": sum(
                1 for m in dela
                if m["status"] == "ativa" and mapa[m["id"]][0].nivel == "evadido"
            ),
        })

    linha_geral = conexao.execute(
        """
        SELECT SUM(CASE WHEN status = 'presente' THEN 1 ELSE 0 END) AS presentes,
               SUM(CASE WHEN status = 'falta'    THEN 1 ELSE 0 END) AS faltas
        FROM presenca WHERE data >= ?
        """,
        (inicio,),
    ).fetchone()
    base_geral = (linha_geral["presentes"] or 0) + (linha_geral["faltas"] or 0)

    pessoas_multi = conexao.execute(
        """
        SELECT COUNT(*) FROM (
            SELECT pessoa_id FROM matricula GROUP BY pessoa_id HAVING COUNT(*) > 1
        )
        """
    ).fetchone()[0]

    total = {
        "matriculas": len(matriculas),
        "pessoas": len({m["pessoa_id"] for m in matriculas}),
        "pessoas_multi": pessoas_multi,
        "em_atividade": sum(c["em_atividade"] for c in cartoes),
        "trazer_de_volta": sum(c["trazer_de_volta"] for c in cartoes),
        "frequencia": (round((linha_geral["presentes"] or 0) / base_geral * 100)
                       if base_geral else 0),
    }
    return {"modalidades": cartoes, "total": total}


def frequencia_mensal(conexao: sqlite3.Connection,
                      modalidade_id: Optional[int] = None) -> list[dict]:
    sql = """
        SELECT strftime('%Y-%m', p.data) AS mes,
               SUM(CASE WHEN p.status = 'presente' THEN 1 ELSE 0 END) AS presentes,
               SUM(CASE WHEN p.status = 'falta'    THEN 1 ELSE 0 END) AS faltas
        FROM presenca p
        JOIN matricula ma ON ma.id = p.matricula_id
        JOIN turma t ON t.id = ma.turma_id
        WHERE 1=1
    """
    parametros: list = []
    if modalidade_id is not None:
        sql += " AND t.modalidade_id = ?"
        parametros.append(modalidade_id)
    sql += " GROUP BY mes ORDER BY mes"

    resultado = []
    for linha in conexao.execute(sql, parametros):
        base = (linha["presentes"] or 0) + (linha["faltas"] or 0)
        ano, mes = linha["mes"].split("-")
        resultado.append({
            "rotulo": f"{MESES_PT[int(mes)]}/{ano[2:]}",
            "percentual": round((linha["presentes"] or 0) / base * 100) if base else 0,
        })
    return resultado


def frequencia_por_turma(conexao: sqlite3.Connection, modalidade_id: int) -> list[dict]:
    inicio = hoje() - timedelta(days=30)
    linhas = conexao.execute(
        """
        SELECT t.id, t.nome AS turma,
               SUM(CASE WHEN p.status = 'presente' THEN 1 ELSE 0 END) AS presentes,
               SUM(CASE WHEN p.status = 'falta'    THEN 1 ELSE 0 END) AS faltas
        FROM presenca p
        JOIN matricula ma ON ma.id = p.matricula_id
        JOIN turma t ON t.id = ma.turma_id
        WHERE p.data >= ? AND t.modalidade_id = ?
        GROUP BY t.id
        """,
        (inicio, modalidade_id),
    ).fetchall()

    # Percorro as turmas cadastradas pra garantir que toda turma apareça no
    # gráfico, mesmo a que não teve aula no período.
    por_id = {l["id"]: l for l in linhas}
    resultado = []
    for turma in turmas_da_modalidade(conexao, modalidade_id):
        linha = por_id.get(turma["id"])
        if linha is None:
            resultado.append({"turma": turma["nome"], "percentual": 0, "vazia": True})
            continue
        base = (linha["presentes"] or 0) + (linha["faltas"] or 0)
        resultado.append({
            "turma": turma["nome"],
            "percentual": round((linha["presentes"] or 0) / base * 100) if base else 0,
            "vazia": False,
        })
    return resultado


def lista_de_contato(conexao: sqlite3.Connection,
                     modalidade_id: Optional[int] = None) -> list[dict]:
    """
    Quem precisa ser contatado, do mais urgente pro menos.

    Eu tinha colocado um limite de 15 aqui. Depois vi que estava escondendo
    alunos da lista sem avisar ninguém, que é exatamente o problema que o
    sistema deveria resolver. Tirei o limite.
    """
    return [m for m in listar_matriculas(conexao, modalidade_id)
            if m["avaliacao"].nivel in ("risco", "evadido")]


# --------------------------------------------------------------- chamada


def datas_recentes(conexao: sqlite3.Connection, modalidade_id: int,
                   limite: int = 20) -> list[date]:
    return [l["data"] for l in conexao.execute(
        """
        SELECT DISTINCT p.data
        FROM presenca p
        JOIN matricula ma ON ma.id = p.matricula_id
        JOIN turma t ON t.id = ma.turma_id
        WHERE t.modalidade_id = ?
        ORDER BY p.data DESC LIMIT ?
        """,
        (modalidade_id, limite),
    )]


def chamada_do_dia(conexao: sqlite3.Connection, turma_id: int, dia: date) -> list[dict]:
    # LEFT JOIN porque preciso listar todas as matrículas da turma, tendo elas
    # registro naquele dia ou não.
    return [dict(l) for l in conexao.execute(
        """
        SELECT ma.id AS matricula_id, ma.status AS matricula_status, ma.numero,
               p.id AS pessoa_id, p.nome, pr.status AS presenca
        FROM matricula ma
        JOIN pessoa p ON p.id = ma.pessoa_id
        LEFT JOIN presenca pr ON pr.matricula_id = ma.id AND pr.data = ?
        WHERE ma.turma_id = ?
        ORDER BY p.nome
        """,
        (dia, turma_id),
    )]


def salvar_chamada(conexao: sqlite3.Connection, dia: date,
                   marcacoes: dict[int, str]) -> int:
    """
    Grava a chamada do dia.

    Usei ON CONFLICT pra dar pra reabrir a mesma data e corrigir. Na primeira
    versão eu fazia DELETE e depois INSERT, e numa hora que o INSERT deu erro
    eu perdi a chamada inteira.
    """
    registros = [
        (matricula_id, dia, status)
        for matricula_id, status in marcacoes.items()
        if status in ("presente", "falta", "justificada")
    ]
    conexao.executemany(
        """
        INSERT INTO presenca (matricula_id, data, status) VALUES (?,?,?)
        ON CONFLICT (matricula_id, data) DO UPDATE SET status = excluded.status
        """,
        registros,
    )
    conexao.commit()
    return len(registros)


# ------------------------------------------------------------- convocação


def listar_eventos(conexao: sqlite3.Connection, modalidade_id: int) -> list[dict]:
    return [dict(l) for l in conexao.execute(
        """
        SELECT e.*, t.nome AS turma_nome, COUNT(c.id) AS convocados
        FROM evento e
        LEFT JOIN turma t ON t.id = e.turma_id
        LEFT JOIN convocacao c ON c.evento_id = e.id
        WHERE e.modalidade_id = ?
        GROUP BY e.id ORDER BY e.data DESC
        """,
        (modalidade_id,),
    )]


def obter_evento(conexao: sqlite3.Connection, evento_id: int) -> Optional[dict]:
    linha = conexao.execute(
        """
        SELECT e.*, t.nome AS turma_nome, m.slug AS modalidade_slug,
               m.nome AS modalidade_nome, m.genero AS modalidade_genero
        FROM evento e
        LEFT JOIN turma t ON t.id = e.turma_id
        JOIN modalidade m ON m.id = e.modalidade_id
        WHERE e.id = ?
        """,
        (evento_id,),
    ).fetchone()
    if linha is None:
        return None

    convocados_ids = {
        r["matricula_id"] for r in conexao.execute(
            "SELECT matricula_id FROM convocacao WHERE evento_id = ?", (evento_id,))
    }

    # Mostro o risco de cada um aqui também, porque o técnico costuma querer
    # chamar justamente quem está faltando, pra trazer o aluno de volta.
    mapa = avaliacoes_e_marcas(conexao, linha["modalidade_id"])
    consulta = f"SELECT {CAMPOS_MATRICULA} {JUNCAO_MATRICULA} WHERE m.id = ?"
    parametros: list = [linha["modalidade_id"]]
    if linha["turma_id"]:
        consulta += " AND ma.turma_id = ?"
        parametros.append(linha["turma_id"])
    consulta += " ORDER BY p.nome"

    elegiveis = []
    for m in conexao.execute(consulta, parametros):
        avaliacao, marcas = mapa[m["matricula_id"]]
        elegiveis.append({
            **dict(m), "avaliacao": avaliacao, "marcas": marcas,
            "convocado": m["matricula_id"] in convocados_ids,
        })

    return {
        **dict(linha),
        "modalidade_exibicao": (
            linha["modalidade_nome"] if linha["modalidade_genero"] == "Misto"
            else f"{linha['modalidade_nome']} {linha['modalidade_genero']}"
        ),
        "elegiveis": elegiveis,
        "convocados": [e for e in elegiveis if e["convocado"]],
    }


def eventos_da_pessoa(conexao: sqlite3.Connection, pessoa_id: int,
                      dias_atras: int = 30) -> list[dict]:
    """
    Os jogos das modalidades em que a pessoa está, e se ela foi convocada.

    Traz também os recentes que já passaram: o jogador quer saber se está
    convocado pro próximo, mas também conferir o último.

    O filtro de turma é o detalhe que importa. Um evento pode ser de uma turma
    específica (Sub-13 joga a Copa) ou da modalidade inteira. Sem o
    `e.turma_id IS NULL OR ...`, um menino do Sub-11 veria o jogo do Sub-17 como
    se fosse dele.
    """
    inicio = hoje() - timedelta(days=dias_atras)
    return [dict(l) for l in conexao.execute(
        """
        SELECT e.*, m.slug AS modalidade_slug, m.nome AS modalidade_nome,
               m.genero AS modalidade_genero, tm.nome AS minha_turma,
               ma.numero,
               CASE WHEN c.id IS NULL THEN 0 ELSE 1 END AS convocado
        FROM evento e
        JOIN modalidade m ON m.id = e.modalidade_id
        JOIN matricula ma ON ma.pessoa_id = ?
        JOIN turma tm     ON tm.id = ma.turma_id
                         AND tm.modalidade_id = e.modalidade_id
        LEFT JOIN convocacao c ON c.evento_id = e.id AND c.matricula_id = ma.id
        WHERE (e.turma_id IS NULL OR e.turma_id = ma.turma_id)
          AND e.data >= ?
        ORDER BY e.data
        """,
        (pessoa_id, inicio),
    )]


def salvar_convocacao(conexao: sqlite3.Connection, evento_id: int,
                      matricula_ids: list[int]) -> None:
    # Apago e regravo tudo. A lista é pequena, então não compensou complicar
    # comparando quem entrou e quem saiu.
    conexao.execute("DELETE FROM convocacao WHERE evento_id = ?", (evento_id,))
    conexao.executemany(
        "INSERT INTO convocacao (evento_id, matricula_id) VALUES (?,?)",
        [(evento_id, m) for m in matricula_ids],
    )
    conexao.commit()


def mensagem_whatsapp(evento: dict) -> str:
    """Monta o texto que o coordenador cola no grupo dos responsáveis."""
    partes = [f"*CONVOCAÇÃO — {evento['nome'].upper()}*", ""]
    if evento["adversario"]:
        partes.append(f"⚽ Adversário: {evento['adversario']}")
    partes += [
        f"📅 Data: {evento['data'].strftime('%d/%m/%Y')}",
        f"📍 Local: {evento['local']}",
    ]
    if evento.get("turma_nome"):
        partes.append(f"👕 Turma: {evento['turma_nome']}")
    partes += ["", f"*Convocados ({len(evento['convocados'])}):*"]
    # Quem tem camisa aparece pelo número, que é como convocação é lida em
    # campo. Mantenho a ordem alfabética e não a numérica de propósito: é a
    # mesma ordem da tela que o técnico está olhando enquanto confere a lista.
    partes += [
        f"{c['numero']} - {c['nome']}" if c.get("numero") else c["nome"]
        for c in evento["convocados"]
    ]

    if evento["observacoes"]:
        partes += ["", f"ℹ️ {evento['observacoes']}"]

    partes += [
        "",
        "Responsáveis, confirmem a presença respondendo aqui no grupo.",
        "_Projeto Social Bola na Rede — Jardim Elizabete_",
    ]
    return "\n".join(partes)


# ----------------------------------------------------------------- agenda


def agenda_do_mes(conexao: sqlite3.Connection, modalidade: dict,
                  ano: int, mes: int) -> dict:
    """
    Monta o calendário do mês de uma modalidade.

    O coordenador me pediu isso depois de ver a chamada: queria olhar o mês
    inteiro e saber em que dias tem aula e em quais ele ainda não fez a
    chamada. Antes ele só descobria que tinha esquecido quando ia montar a
    convocação e faltava registro.
    """
    dias_com_aula = {int(d) for d in modalidade["dias_aula"].split(",")}

    primeiro = date(ano, mes, 1)
    proximo_mes = (primeiro + timedelta(days=32)).replace(day=1)
    ultimo = proximo_mes - timedelta(days=1)

    lancamentos = {
        l["data"]: l for l in conexao.execute(
            """
            SELECT p.data, COUNT(*) AS registros,
                   SUM(CASE WHEN p.status = 'presente' THEN 1 ELSE 0 END) AS presentes
            FROM presenca p
            JOIN matricula ma ON ma.id = p.matricula_id
            JOIN turma t ON t.id = ma.turma_id
            WHERE t.modalidade_id = ? AND p.data BETWEEN ? AND ?
            GROUP BY p.data
            """,
            (modalidade["id"], primeiro, ultimo),
        )
    }

    eventos_do_mes: dict[date, list[dict]] = {}
    for linha in conexao.execute(
        """
        SELECT e.*, t.nome AS turma_nome FROM evento e
        LEFT JOIN turma t ON t.id = e.turma_id
        WHERE e.modalidade_id = ? AND e.data BETWEEN ? AND ?
        ORDER BY e.data
        """,
        (modalidade["id"], primeiro, ultimo),
    ):
        eventos_do_mes.setdefault(linha["data"], []).append(dict(linha))

    # Semanas começando na segunda, incluindo os dias das pontas que caem em
    # outro mês, pra grade não ficar com buraco.
    semanas: list[list[dict]] = []
    referencia = hoje()
    cursor_dia = primeiro - timedelta(days=primeiro.weekday())
    while cursor_dia <= ultimo or cursor_dia.weekday() != 0:
        if cursor_dia.weekday() == 0:
            semanas.append([])
        lancamento = lancamentos.get(cursor_dia)
        semanas[-1].append({
            "data": cursor_dia,
            "no_mes": cursor_dia.month == mes,
            "hoje": cursor_dia == referencia,
            "futuro": cursor_dia > referencia,
            "tem_aula": cursor_dia.weekday() in dias_com_aula and cursor_dia.month == mes,
            "chamada_feita": lancamento is not None,
            "presentes": lancamento["presentes"] if lancamento else 0,
            "eventos": eventos_do_mes.get(cursor_dia, []),
        })
        cursor_dia += timedelta(days=1)
        if len(semanas) > 6:
            break

    esquecidas = [d for semana in semanas for d in semana
                  if d["tem_aula"] and not d["futuro"] and not d["chamada_feita"]]

    return {
        "rotulo": f"{MESES_NOME[mes]} de {ano}",
        "semanas": semanas,
        "dias_semana": DIAS_SEMANA_CURTO,
        "mes_anterior": (primeiro - timedelta(days=1)).strftime("%Y-%m"),
        "mes_seguinte": proximo_mes.strftime("%Y-%m"),
        "total_aulas": sum(1 for s in semanas for d in s if d["tem_aula"]),
        "esquecidas": esquecidas,
        "eventos": [e for lista in eventos_do_mes.values() for e in lista],
    }
