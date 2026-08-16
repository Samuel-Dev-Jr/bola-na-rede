"""Conexão com o banco SQLite."""

import re
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

    A chave estrangeira fica desligada durante a derrubada: a plano_treino, que
    nasceu no migracoes.sql, aponta pra turma, e com a chave ligada o DROP da
    turma era recusado e o configurar parava.
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
    texto = CAMINHO_MIGRACOES.read_text(encoding="utf-8")
    return re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", texto)


# Colunas que nasceram depois do schema. ALTER TABLE não tem IF NOT EXISTS no
# SQLite, então o aplicar_migracoes confere o PRAGMA antes de alterar.
COLUNAS_NOVAS = [
    ("pessoa", "email", "TEXT"),
    ("usuario", "avisos_vistos_em", "TEXT"),
]


def aplicar_migracoes() -> None:
    """
    Cria o que veio depois do schema original, sem apagar nada. Roda a cada
    início; se o banco já está em dia, não faz nada.
    """
    conexao = conectar()
    try:
        conexao.executescript(CAMINHO_MIGRACOES.read_text(encoding="utf-8"))
        for tabela, coluna, tipo in COLUNAS_NOVAS:
            existentes = {l["name"] for l in
                          conexao.execute(f"PRAGMA table_info({tabela})")}
            if coluna not in existentes:
                conexao.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo}")
        conexao.commit()
    finally:
        conexao.close()


def banco_existe() -> bool:
    return CAMINHO_BANCO.exists()
