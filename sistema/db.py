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
    """Apaga tudo e cria as tabelas de novo. Só o configurar.py usa isso."""
    conexao = conectar()
    try:
        conexao.executescript(CAMINHO_SCHEMA.read_text(encoding="utf-8"))
        conexao.commit()
    finally:
        conexao.close()


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
