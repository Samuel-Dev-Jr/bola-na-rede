"""
Importa cadastro e chamada de planilha CSV para o banco.

  matriculas.csv  uma linha por matrícula. Quem faz duas atividades aparece em
                  duas linhas; o importador junta por nome + nascimento e cria
                  UMA pessoa com DUAS matrículas.
  presencas.csv   formato largo, igual à folha de papel: uma coluna por data,
                  P/F/J na célula. Vazia = sem registro, que não é falta.

Reimportar não duplica nada, então dá pra corrigir a planilha e mandar de novo.
Linha sem dado obrigatório é recusada com o motivo — o importador não inventa
nada. Tudo devolve um Resultado em vez de imprimir, senão o segundo upload na
tela mostraria os erros do primeiro.

Pelo terminal:  python importar.py dados/matriculas.csv [dados/presencas.csv]
"""

import csv
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import db
from configurar import faixa_da_turma
from consultas import idade

STATUS_PRESENCA = {
    "p": "presente", "presente": "presente",
    "f": "falta", "falta": "falta",
    "j": "justificada", "justificada": "justificada",
}

OBRIGATORIAS_MATRICULA = [
    "nome", "data_nascimento", "responsavel_nome",
    "responsavel_parentesco", "responsavel_telefone",
    "modalidade_slug", "turma",
]

OPCIONAIS_PESSOA = [
    "emergencia_nome", "emergencia_telefone", "alergias", "condicoes",
    "medicacao_continua", "plano_saude", "observacoes_medicas",
]

COLUNAS_FIXAS_PRESENCA = {"modalidade_slug", "turma", "nome", "data_nascimento"}


@dataclass
class Resultado:
    """O que aconteceu num import. Serve pro terminal e pra tela."""

    resumo: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    erros: list[str] = field(default_factory=list)
    pessoas_novas: int = 0
    matriculas: int = 0
    presencas: int = 0

    @property
    def ok(self) -> bool:
        return not self.erros


def decodificar(bruto: bytes) -> str | None:
    """
    O Excel em português às vezes salva em cp1252 em vez de UTF-8. Tento os dois
    em vez de exigir que o arquivo esteja "certo".
    """
    for codificacao in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            return bruto.decode(codificacao)
        except UnicodeDecodeError:
            continue
    return None


def separar(texto: str) -> list[dict]:
    """
    Vira as linhas do CSV em dicionários de chave minúscula.

    O Excel em português salva separado por ponto e vírgula. Detecto pela
    primeira linha em vez de exigir vírgula.
    """
    linhas_texto = texto.splitlines()
    if not linhas_texto:
        return []

    primeira = linhas_texto[0]
    separador = ";" if primeira.count(";") > primeira.count(",") else ","

    return [
        {(k or "").strip().lower(): (v or "").strip() for k, v in linha.items()}
        for linha in csv.DictReader(linhas_texto, delimiter=separador)
    ]


def _data_de(texto: str, onde: str, res: Resultado) -> date | None:
    try:
        return date.fromisoformat(texto)
    except ValueError:
        res.erros.append(f"{onde}: data inválida {texto!r} (use AAAA-MM-DD)")
        return None


def _resolver_turma(conexao, slug: str, turma_nome: str, onde: str,
                    res: Resultado) -> int | None:
    linha = conexao.execute(
        """
        SELECT t.id FROM turma t
        JOIN modalidade m ON m.id = t.modalidade_id
        WHERE m.slug = ? AND t.nome = ?
        """,
        (slug, turma_nome),
    ).fetchone()
    if linha:
        return linha["id"]

    if not conexao.execute("SELECT 1 FROM modalidade WHERE slug = ?", (slug,)).fetchone():
        res.erros.append(f"{onde}: modalidade {slug!r} não existe. "
                         f"Confira o slug na planilha.")
    else:
        turmas = [r["nome"] for r in conexao.execute(
            """SELECT t.nome FROM turma t JOIN modalidade m ON m.id = t.modalidade_id
               WHERE m.slug = ? ORDER BY t.ordem""", (slug,))]
        res.erros.append(f"{onde}: turma {turma_nome!r} não existe em {slug}. "
                         f"Turmas: {', '.join(turmas)}")
    return None


# ------------------------------------------------------------- matrículas


def importar_matriculas(conexao, nome_arquivo: str, linhas: list[dict],
                        res: Resultado) -> None:
    res.resumo.append(f"{nome_arquivo}: {len(linhas)} linha(s) de matrícula")

    pessoas_vistas: dict[tuple, int] = {}

    # TODA a validação acontece antes de qualquer INSERT. A primeira versão
    # criava a pessoa e só depois checava o número da camisa: linha recusada
    # deixava uma pessoa sem nenhuma matrícula no banco, e o relatório dizia
    # "essas linhas não entraram", o que passou a ser mentira. Agora linha
    # recusada não deixa rastro.
    for numero_linha, linha in enumerate(linhas, 2):  # 2 = primeira linha de dados
        onde = f"{nome_arquivo} linha {numero_linha}"

        faltando = [c for c in OBRIGATORIAS_MATRICULA if not linha.get(c)]
        if faltando:
            res.erros.append(f"{onde}: falta preencher {', '.join(faltando)}")
            continue

        nascimento = _data_de(linha["data_nascimento"], onde, res)
        if nascimento is None:
            continue

        turma_id = _resolver_turma(conexao, linha["modalidade_slug"],
                                   linha["turma"], onde, res)
        if turma_id is None:
            continue

        data_matricula = (_data_de(linha["data_matricula"], onde, res)
                          if linha.get("data_matricula") else date.today())
        if data_matricula is None:
            continue

        status = linha.get("status") or "ativa"
        if status not in ("ativa", "encerrada"):
            res.erros.append(f"{onde}: status {status!r} (use ativa ou encerrada)")
            continue

        numero = None
        if linha.get("numero"):
            try:
                numero = int(linha["numero"])
            except ValueError:
                res.erros.append(f"{onde}: número {linha['numero']!r} não é inteiro")
                continue
            if not 1 <= numero <= 99:
                res.erros.append(f"{onde}: número {numero} fora da faixa 1 a 99")
                continue

        # A idade contra a faixa da turma é aviso, não erro: a coordenação às
        # vezes deixa alguém treinar numa categoria acima, e não sou eu que vou
        # recusar o cadastro por isso. Mas fica registrado.
        faixa = faixa_da_turma(linha["modalidade_slug"], linha["turma"])
        anos = idade(nascimento)
        if faixa and not (faixa[0] <= anos <= faixa[1]):
            res.avisos.append(f"{onde}: {linha['nome']} tem {anos} anos e "
                              f"{linha['turma']} é de {faixa[0]} a {faixa[1]}")

        # Só LOCALIZO a pessoa aqui; a criação vem depois de tudo validado.
        chave = (linha["nome"].casefold(), nascimento)
        pessoa_id = pessoas_vistas.get(chave)
        if pessoa_id is None:
            existente = conexao.execute(
                "SELECT id FROM pessoa WHERE nome = ? AND data_nascimento = ?",
                (linha["nome"], nascimento),
            ).fetchone()
            pessoa_id = existente["id"] if existente else None

        if numero is not None:
            # Confiro aqui pra poder dizer COM QUEM o número está. O índice
            # único do banco também pegaria, mas com uma mensagem que não ajuda
            # ninguém a corrigir a planilha.
            #
            # O `? IS NULL OR` no fim é pra reimportar a mesma planilha não
            # acusar a pessoa de tomar o número dela mesma.
            dono = conexao.execute(
                """
                SELECT p.nome FROM matricula ma
                JOIN pessoa p ON p.id = ma.pessoa_id
                WHERE ma.turma_id = ? AND ma.numero = ?
                  AND (? IS NULL OR ma.pessoa_id <> ?)
                """,
                (turma_id, numero, pessoa_id, pessoa_id),
            ).fetchone()
            if dono:
                res.erros.append(f"{onde}: a camisa {numero} de {linha['turma']} "
                                 f"já está com {dono['nome']}")
                continue

        if pessoa_id is None:
            colunas = ["nome", "data_nascimento", "responsavel_nome",
                       "responsavel_parentesco", "responsavel_telefone",
                       "autoriza_imagem"] + OPCIONAIS_PESSOA
            valores = [
                linha["nome"], nascimento, linha["responsavel_nome"],
                linha["responsavel_parentesco"], linha["responsavel_telefone"],
                1 if linha.get("autoriza_imagem", "").strip() in ("1", "sim", "s") else 0,
            ] + [linha.get(c) or None for c in OPCIONAIS_PESSOA]

            cursor = conexao.execute(
                f"INSERT INTO pessoa ({', '.join(colunas)}) "
                f"VALUES ({', '.join('?' * len(colunas))})",
                valores,
            )
            pessoa_id = cursor.lastrowid
            res.pessoas_novas += 1
        pessoas_vistas[chave] = pessoa_id

        antes = conexao.total_changes
        conexao.execute(
            """
            INSERT INTO matricula (pessoa_id, turma_id, data_matricula, status, numero)
            VALUES (?,?,?,?,?)
            ON CONFLICT (pessoa_id, turma_id) DO UPDATE
              SET data_matricula = excluded.data_matricula,
                  status = excluded.status,
                  numero = excluded.numero
            """,
            (pessoa_id, turma_id, data_matricula, status, numero),
        )
        if conexao.total_changes > antes:
            res.matriculas += 1

    conexao.commit()
    res.resumo.append(f"  {res.pessoas_novas} pessoa(s) nova(s), "
                      f"{res.matriculas} matrícula(s) gravada(s)")


# --------------------------------------------------------------- presenças


def importar_presencas(conexao, nome_arquivo: str, linhas: list[dict],
                       res: Resultado) -> None:
    if not linhas:
        res.erros.append(f"{nome_arquivo}: planilha vazia")
        return

    colunas_data = [c for c in linhas[0] if c and c not in COLUNAS_FIXAS_PRESENCA]
    res.resumo.append(f"{nome_arquivo}: {len(linhas)} linha(s), "
                      f"{len(colunas_data)} coluna(s) de data")
    if not colunas_data:
        res.erros.append(f"{nome_arquivo}: nenhuma coluna de data no cabeçalho. "
                         f"Cada data é uma coluna, no formato AAAA-MM-DD.")
        return

    hoje = date.today()
    vazias = 0

    for numero_linha, linha in enumerate(linhas, 2):
        onde = f"{nome_arquivo} linha {numero_linha}"
        if not linha.get("nome"):
            continue

        turma_id = _resolver_turma(conexao, linha.get("modalidade_slug", ""),
                                   linha.get("turma", ""), onde, res)
        if turma_id is None:
            continue

        matricula = conexao.execute(
            """
            SELECT ma.id FROM matricula ma
            JOIN pessoa p ON p.id = ma.pessoa_id
            WHERE ma.turma_id = ? AND p.nome = ?
            """,
            (turma_id, linha["nome"]),
        ).fetchall()

        if not matricula:
            res.erros.append(f"{onde}: {linha['nome']!r} não tem matrícula em "
                             f"{linha.get('turma')}. Importe as matrículas primeiro.")
            continue
        if len(matricula) > 1:
            res.erros.append(f"{onde}: há {len(matricula)} pessoas chamadas "
                             f"{linha['nome']!r} nessa turma. Desambigue na planilha.")
            continue
        matricula_id = matricula[0]["id"]

        for coluna in colunas_data:
            valor = (linha.get(coluna) or "").strip().casefold()
            if not valor:
                vazias += 1
                continue

            status = STATUS_PRESENCA.get(valor)
            if status is None:
                res.erros.append(f"{onde}, coluna {coluna}: valor {valor!r} "
                                 f"(use P, F ou J)")
                continue

            dia = _data_de(coluna, f"{nome_arquivo} cabeçalho", res)
            if dia is None:
                continue
            if dia > hoje:
                res.avisos.append(f"{nome_arquivo}: a coluna {coluna} está no "
                                  f"futuro; o cálculo de risco vai ignorá-la")

            conexao.execute(
                """
                INSERT INTO presenca (matricula_id, data, status) VALUES (?,?,?)
                ON CONFLICT (matricula_id, data) DO UPDATE
                  SET status = excluded.status
                """,
                (matricula_id, dia, status),
            )
            res.presencas += 1

    conexao.commit()
    res.resumo.append(f"  {res.presencas} presença(s) gravada(s), "
                      f"{vazias} célula(s) vazia(s) ignorada(s)")


# ---------------------------------------------------------------- entrada


def importar_texto(conexao, nome_arquivo: str, texto: str,
                   res: Resultado | None = None) -> Resultado:
    """
    Importa a partir do CONTEÚDO da planilha, sem passar pelo disco.

    É por aqui que a tela de Configurações entra: ela recebe o arquivo enviado
    pelo navegador e passa o texto direto, sem gravar nada em pasta nenhuma.

    Escolho entre matrícula e presença pelo nome do arquivo, porque as duas
    planilhas têm formatos diferentes e confundir uma com a outra produziria
    erro em cascata.
    """
    res = res or Resultado()
    linhas = separar(texto)
    if not linhas:
        res.erros.append(f"{nome_arquivo}: não achei nenhuma linha de dados")
        return res

    if "presenc" in nome_arquivo.casefold():
        importar_presencas(conexao, nome_arquivo, linhas, res)
    else:
        importar_matriculas(conexao, nome_arquivo, linhas, res)
    return res


def importar_arquivo(conexao, caminho: Path, res: Resultado) -> None:
    bruto = caminho.read_bytes()
    texto = decodificar(bruto)
    if texto is None:
        res.erros.append(f"{caminho.name}: não consegui ler (codificação)")
        return
    importar_texto(conexao, caminho.name, texto, res)


def estado_do_banco(conexao) -> dict:
    """Os números que a tela de Configurações mostra antes e depois do import."""
    def conta(tabela):
        return conexao.execute(f"SELECT COUNT(*) c FROM {tabela}").fetchone()["c"]

    datas = conexao.execute(
        "SELECT MIN(data) a, MAX(data) b FROM presenca"
    ).fetchone()
    return {
        "modalidades": conta("modalidade"),
        "turmas": conta("turma"),
        "pessoas": conta("pessoa"),
        "matriculas": conta("matricula"),
        "presencas": conta("presenca"),
        "eventos": conta("evento"),
        "primeira_chamada": datas["a"],
        "ultima_chamada": datas["b"],
    }


def main(caminhos: list[str]) -> int:
    if not caminhos:
        print(__doc__)
        return 2

    if not db.banco_existe():
        print("Banco não encontrado. Rode `python configurar.py` primeiro.")
        return 1

    res = Resultado()
    conexao = db.conectar()
    try:
        for texto in caminhos:
            caminho = Path(texto)
            if not caminho.exists():
                res.erros.append(f"{texto}: arquivo não encontrado")
                continue
            importar_arquivo(conexao, caminho, res)
        estado = estado_do_banco(conexao)
    finally:
        conexao.close()

    for linha in res.resumo:
        print(linha)

    if res.avisos:
        print(f"\n--- {len(res.avisos)} aviso(s) (importei, mas confira) ---")
        for a in res.avisos:
            print(f"  {a}")

    if res.erros:
        print(f"\n--- {len(res.erros)} erro(s) (essas linhas NÃO entraram) ---")
        for e in res.erros:
            print(f"  {e}")

    print(f"\nBanco agora: {estado['pessoas']} pessoa(s), "
          f"{estado['matriculas']} matrícula(s), {estado['presencas']} presença(s)")
    if estado["primeira_chamada"]:
        print(f"Chamada de {estado['primeira_chamada']} até {estado['ultima_chamada']}")
    print("Confira com: python metricas.py")

    return 0 if res.ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
