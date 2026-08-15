"""
Calcula as métricas de impacto do projeto, lendo o banco na hora.

Eu fiz este script em vez de escrever os números num documento porque número
escrito à mão em relatório ninguém consegue conferir. Aqui é só rodar
`python metricas.py` e ele recalcula tudo do `centro.db` na frente de
quem estiver olhando.

A procedência de cada número está declarada junto dele, porque isso muda o peso
que ele tem:

  CONTADO   — vem de contar linhas no banco. É fato.
  DERIVADO  — vem de percorrer o calendário aplicando a própria regra de risco.
              Não é medição de campo, é uma propriedade da regra, e dá pra
              conferir lendo o risco.py.
  RELATADO  — foi a coordenação que me disse. Não medi, e por isso está
              marcado assim: serve de contexto, não de prova.

O que este script NÃO faz: as duas métricas de cronômetro (tempo da chamada no
papel contra o sistema, e tempo pra achar um contato de emergência). Essas só
existem indo ao Centro com um cronômetro, e ficam registradas à parte.
"""

import db
from risco import FALTAS_CONSECUTIVAS_ATENCAO, FALTAS_CONSECUTIVAS_RISCO

# Palavras que identificam as colunas de ficha médica na tabela pessoa. Descubro
# as colunas pelo PRAGMA em vez de listar na mão, senão o dia que eu acrescentar
# um campo no schema este script passa a mentir por omissão.
MARCAS_FICHA_MEDICA = ("alergia", "condicao", "medica", "emergencia", "sangue")

LARGURA = 68


def titulo(numero: str, texto: str) -> None:
    print("\n" + "=" * LARGURA)
    print(f"{numero}. {texto}")
    print("=" * LARGURA)


def dias_ate_acumular(dias_treino: set[int], faltas: int) -> tuple[int, int]:
    """
    Quantos dias corridos a regra leva pra juntar N faltas seguidas.

    Conto do dia da última presença até a falta que dispara o alerta. O
    resultado varia conforme o dia da semana em que a última presença caiu —
    faltar na sexta de uma turma de segunda e quarta custa mais dias de
    calendário que faltar na segunda. Por isso devolvo o melhor e o pior caso,
    em vez de uma média que não corresponde a nenhuma criança real.
    """
    intervalos = []
    for inicio in range(7):
        acumuladas = 0
        for adiante in range(1, 60):
            if (inicio + adiante) % 7 in dias_treino:
                acumuladas += 1
                if acumuladas == faltas:
                    intervalos.append(adiante)
                    break
    return min(intervalos), max(intervalos)


conexao = db.conectar()

# ------------------------------------------------- 1. qualidade dos dados
titulo("1", "QUALIDADE DOS DADOS  [CONTADO]")

pessoas = conexao.execute("SELECT COUNT(*) c FROM pessoa").fetchone()["c"]
matriculas = conexao.execute("SELECT COUNT(*) c FROM matricula").fetchone()["c"]
em_duas_ou_mais = conexao.execute(
    """
    SELECT COUNT(*) c FROM (
      SELECT pessoa_id FROM matricula GROUP BY pessoa_id HAVING COUNT(*) > 1
    )
    """
).fetchone()["c"]

duplicados = matriculas - pessoas

print(f"  pessoas cadastradas ..................... {pessoas}")
print(f"  matrículas (pessoa x turma) ............. {matriculas}")
print(f"  pessoas em mais de uma atividade ........ {em_duas_ou_mais}")
print()

if matriculas == 0:
    print("  Base vazia: não há o que contar ainda. Cadastre pessoas pela tela")
    print("  ou importe a planilha antes de usar este bloco no relatório.")
    print("  Zero aqui não é resultado — é ausência de dado.")
else:
    print("  O modelo antigo guardava uma linha de aluno por modalidade. Com a")
    print(f"  base atual ele teria {matriculas} cadastros de pessoa "
          f"para {pessoas} pessoas:")
    print(f"    -> {duplicados} cadastros duplicados "
          f"({duplicados / matriculas:.1%} das linhas)")
    print(f"    -> {em_duas_ou_mais} pessoas com ficha médica repetida, "
          f"livre pra divergir")

# ------------------------------------------------------- 2. ficha médica
titulo("2", "FICHA MÉDICA ACESSÍVEL NO CAMPO  [CONTADO]")

colunas_medicas = [
    coluna[1] for coluna in conexao.execute("PRAGMA table_info(pessoa)")
    if any(marca in coluna[1] for marca in MARCAS_FICHA_MEDICA)
]

# Leio as pessoas uma vez e conto em Python. Fazer um COUNT por coluna exigiria
# montar o nome da coluna dentro do SQL, e eu prefiro não escrever SQL por
# concatenação nem quando a origem é segura.
todas = conexao.execute("SELECT * FROM pessoa").fetchall()

if pessoas == 0:
    print(f"  colunas de ficha médica: {', '.join(colunas_medicas)}")
    print("  Base vazia: nada preenchido porque nada foi cadastrado.")
else:
    for coluna in colunas_medicas:
        preenchidos = sum(
            1 for linha in todas
            if linha[coluna] is not None and str(linha[coluna]).strip() != ""
        )
        faltando = pessoas - preenchidos
        alerta = ("   <-- pendência pra coordenação"
                  if coluna.startswith("emergencia") and faltando else "")
        print(f"  {coluna:<24} {preenchidos:>3}/{pessoas}"
              f"   (faltam {faltando}){alerta}")

    print()
    print("  No caderno de papel não havia como responder quantas fichas estavam")
    print("  incompletas. Essa contagem é resultado do sistema, não do relatório.")

# ------------------------------------------------ 3. latência de detecção
titulo("3", "LATÊNCIA DE DETECÇÃO DA EVASÃO  [DERIVADO da regra]")

print(f"  Faltas seguidas pra 'atenção': {FALTAS_CONSECUTIVAS_ATENCAO}"
      f"  |  pra 'risco de evasão': {FALTAS_CONSECUTIVAS_RISCO}")
print("  Abaixo, os dias corridos entre a última presença e o alerta.")
print()
print(f"  {'Modalidade':<24}{'/semana':<9}{'Atenção':<14}{'Risco'}")
print("  " + "-" * (LARGURA - 4))

for modalidade in conexao.execute(
    "SELECT nome, genero, dias_aula FROM modalidade ORDER BY id"
):
    dias_treino = {int(d) for d in modalidade["dias_aula"].split(",")}
    atencao = dias_ate_acumular(dias_treino, FALTAS_CONSECUTIVAS_ATENCAO)
    risco = dias_ate_acumular(dias_treino, FALTAS_CONSECUTIVAS_RISCO)
    nome = f"{modalidade['nome']} {modalidade['genero'] or ''}".strip()
    print(f"  {nome:<24}{len(dias_treino)}x{'':<7}"
          f"{atencao[0]}-{atencao[1]} dias{'':<6}"
          f"{risco[0]}-{risco[1]} dias")

print()
print("  A meta que eu combinei com a coordenação era avisar em uma semana.")
print("  Nas modalidades de 3x por semana o alerta de risco sai em 5 a 7 dias.")
print()
print("  [RELATADO] Hoje a escolinha descobre que a criança parou de vir quando")
print("  alguém comenta no treino — cerca de dois meses, segundo a coordenação.")
print("  Esse número eu não medi, e está marcado como relato de propósito.")

print("\n" + "=" * LARGURA)
print("As duas métricas de cronômetro (chamada e busca de contato, papel contra")
print("sistema) não estão aqui: elas precisam de medição no Centro.")
print("=" * LARGURA)

conexao.close()
