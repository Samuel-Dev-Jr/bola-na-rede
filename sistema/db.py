"""Conexão com o banco SQLite."""

import sqlite3
from datetime import date
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CAMINHO_BANCO = BASE_DIR / "centro.db"
CAMINHO_SCHEMA = BASE_DIR / "schema.sql"
CAMINHO_MIGRACOES = BASE_DIR / "migracoes.sql"

# O Python 3.12 marcou como obsoleto o jeito antigo do sqlite3 converter datas,
# e aparecia um monte de aviso no terminal. Registrei os meus: gravo a data
# como texto ISO e leio de volta como date.
sqlite3.register_adapter(date, lambda d: d.isoformat())
sqlite3.register_converter("DATE", lambda bruto: date.fromisoformat(bruto.decode()))


def conectar() -> sqlite3.Connection:
    conexao = sqlite3.connect(CAMINHO_BANCO, detect_types=sqlite3.PARSE_DECLTYPES)
    # row_factory pra eu poder acessar as colunas pelo nome (linha["nome"])
    # em vez de por número, que fica ilegível.
    conexao.row_factory = sqlite3.Row
    conexao.execute("PRAGMA foreign_keys = ON")
    return conexao


def recriar_schema() -> None:
    """
    Apaga tudo e cria as tabelas de novo. Só o configurar.py usa isso.

    Desligo a chave estrangeira aqui, e não é preguiça. O schema.sql só conhece
    as tabelas originais; a plano_treino nasceu no migracoes.sql e aponta pra
    turma. Com a chave ligada, o DROP TABLE turma era recusado — "no such table:
    main.turma" — e o configurar.py parava de rodar em qualquer banco que já
    tivesse migração aplicada. Ou seja: quanto mais o sistema evoluía, menos ele
    conseguia se recriar.

    A alternativa seria listar as tabelas novas no schema.sql, mas aí os dois
    arquivos passariam a depender um do outro e eu teria que lembrar de mexer
    nos dois a cada tabela nova. Desligar a checagem enquanto derrubo tudo é o
    que essa operação significa de verdade.
    """
    conexao = conectar()
    try:
        conexao.execute("PRAGMA foreign_keys = OFF")
        for tabela in tabelas_extras():
            conexao.execute(f"DROP TABLE IF EXISTS {tabela}")
        conexao.executescript(CAMINHO_SCHEMA.read_text(encoding="utf-8"))
        conexao.commit()
    finally:
        conexao.close()


def tabelas_extras() -> list[str]:
    """As tabelas criadas pelo migracoes.sql, lidas do próprio arquivo."""
    import re
    texto = CAMINHO_MIGRACOES.read_text(encoding="utf-8")
    return re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", texto)


def aplicar_migracoes() -> None:
    """
    Cria o que veio depois do schema original, sem apagar nada.

    O schema.sql começa com DROP TABLE, então só serve pra banco novo. Rodar ele
    no computador do Centro apagaria a chamada digitada na tela, que não existe
    em planilha nenhuma — descobri isso quando fui criar a tabela de planos.

    Pode chamar quantas vezes quiser: se o banco já está em dia, não faz nada.
    """
    conexao = conectar()
    try:
        conexao.executescript(CAMINHO_MIGRACOES.read_text(encoding="utf-8"))
        conexao.commit()
    finally:
        conexao.close()


def banco_existe() -> bool:
    return CAMINHO_BANCO.exists()
