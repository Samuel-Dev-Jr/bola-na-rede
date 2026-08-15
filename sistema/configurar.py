"""
Monta o banco vazio com a estrutura do Centro: modalidades e turmas.

Este script NÃO cria pessoa, matrícula nem presença. Ele só grava o que o Centro
é: quais atividades existem, em que dias e horários cada uma acontece, e em que
turmas ela se divide. Isso não é dado de teste — é a configuração da escolinha,
levantada com a coordenação, e é o que precisa existir antes de qualquer pessoa
ser cadastrada, porque matrícula aponta pra turma.

As pessoas entram depois, pela tela de cadastro ou pelo importador de CSV.

Pra rodar:  python configurar.py

Cuidado: ele recria o schema, ou seja, APAGA tudo que estiver no banco. É o que
se quer na primeira vez; depois disso, rodar de novo zera o cadastro.
"""

import db

# Os dias da semana seguem o padrão do Python: 0 = segunda ... 6 = domingo.
# Guardo como texto separado por vírgula porque é o formato que o
# consultas.proxima_data_de_aula() já espera.
#
# A faixa de idade de cada turma não vai pro banco — a tabela turma só tem nome
# e ordem. Ela fica registrada aqui porque é a regra que a coordenação usa pra
# dizer em que turma uma criança entra, e o importador de CSV vai precisar dela
# pra recusar matrícula em turma que não corresponde à idade.
MODALIDADES = [
    {
        "slug": "futebol-masculino", "nome": "Futebol", "genero": "Masculino",
        "descricao": "Categorias de base e várzea",
        "cor": "#0f7a3d", "icone": "futebol",
        "dias_aula": "1,3,5", "horario": "Ter e Qui, 18h às 20h · Sáb, 8h às 11h",
        "tem_convocacao": 1,
        "termo_aluno": "atleta", "termo_aula": "treino",
        "termo_aula_pl": "treinos", "artigo_aula": "um",
        "turmas": [
            ("Sub-11", (9, 11)), ("Sub-13", (12, 13)),
            ("Sub-15", (14, 15)), ("Sub-17", (16, 17)),
        ],
    },
    {
        "slug": "futebol-feminino", "nome": "Futebol", "genero": "Feminino",
        "descricao": "Time feminino de base",
        "cor": "#0f7a3d", "icone": "futebol",
        "dias_aula": "0,2", "horario": "Seg e Qua, 18h às 20h",
        "tem_convocacao": 1,
        "termo_aluno": "atleta", "termo_aula": "treino",
        "termo_aula_pl": "treinos", "artigo_aula": "um",
        "turmas": [("Sub-13", (10, 13)), ("Sub-15", (14, 15)), ("Sub-17", (16, 17))],
    },
    {
        "slug": "volei-masculino", "nome": "Vôlei", "genero": "Masculino",
        "descricao": "Quadra coberta, base e adulto",
        "cor": "#1d5fbf", "icone": "volei",
        "dias_aula": "1,3", "horario": "Ter e Qui, 19h às 21h",
        "tem_convocacao": 1,
        "termo_aluno": "atleta", "termo_aula": "treino",
        "termo_aula_pl": "treinos", "artigo_aula": "um",
        "turmas": [("Sub-14", (11, 14)), ("Sub-16", (15, 16)), ("Adulto", (18, 60))],
    },
    {
        "slug": "volei-feminino", "nome": "Vôlei", "genero": "Feminino",
        "descricao": "Quadra coberta, base e adulto",
        "cor": "#1d5fbf", "icone": "volei",
        "dias_aula": "0,2", "horario": "Seg e Qua, 19h às 21h",
        "tem_convocacao": 1,
        "termo_aluno": "atleta", "termo_aula": "treino",
        "termo_aula_pl": "treinos", "artigo_aula": "um",
        "turmas": [("Sub-14", (11, 14)), ("Sub-16", (15, 16)), ("Adulto", (18, 60))],
    },
    {
        "slug": "basquete-masculino", "nome": "Basquete", "genero": "Masculino",
        "descricao": "Iniciação e categorias de base",
        "cor": "#c2410c", "icone": "basquete",
        "dias_aula": "0,2", "horario": "Seg e Qua, 16h às 18h",
        "tem_convocacao": 1,
        "termo_aluno": "atleta", "termo_aula": "treino",
        "termo_aula_pl": "treinos", "artigo_aula": "um",
        "turmas": [("Sub-14", (11, 14)), ("Sub-16", (15, 17))],
    },
    {
        "slug": "basquete-feminino", "nome": "Basquete", "genero": "Feminino",
        "descricao": "Iniciação e categorias de base",
        "cor": "#c2410c", "icone": "basquete",
        "dias_aula": "1,3", "horario": "Ter e Qui, 16h às 18h",
        "tem_convocacao": 1,
        "termo_aluno": "atleta", "termo_aula": "treino",
        "termo_aula_pl": "treinos", "artigo_aula": "um",
        "turmas": [("Sub-14", (11, 14)), ("Sub-16", (15, 17))],
    },
    {
        "slug": "karate", "nome": "Karatê", "genero": "Misto",
        "descricao": "Turmas por faixa, do branco ao verde",
        "cor": "#6d28d9", "icone": "karate",
        "dias_aula": "0,2,4", "horario": "Seg, Qua e Sex, 17h às 18h30",
        "tem_convocacao": 0,
        "termo_aluno": "aluno", "termo_aula": "aula",
        "termo_aula_pl": "aulas", "artigo_aula": "uma",
        "turmas": [
            ("Faixa branca", (8, 12)), ("Faixa amarela", (10, 14)),
            ("Faixa laranja", (12, 16)), ("Faixa verde", (14, 17)),
        ],
    },
    {
        "slug": "pilates", "nome": "Pilates", "genero": "Misto",
        "descricao": "Mães, pais e terceira idade do bairro",
        "cor": "#0e7490", "icone": "pilates",
        "dias_aula": "0,2,4", "horario": "Seg, Qua e Sex, manhã e noite",
        "tem_convocacao": 0,
        "termo_aluno": "aluno", "termo_aula": "aula",
        "termo_aula_pl": "aulas", "artigo_aula": "uma",
        "turmas": [
            ("Turma da manhã", (30, 78)), ("Turma da tarde", (30, 78)),
            ("Turma da noite", (30, 60)),
        ],
    },
]


def faixa_da_turma(slug: str, turma_nome: str) -> tuple[int, int] | None:
    """A faixa de idade de uma turma, pro importador validar a matrícula."""
    for modalidade in MODALIDADES:
        if modalidade["slug"] == slug:
            for nome, faixa in modalidade["turmas"]:
                if nome == turma_nome:
                    return faixa
    return None


def configurar() -> None:
    print("Recriando o schema (isso apaga o que estiver no banco)...")
    db.recriar_schema()

    # O schema.sql tem só as tabelas originais; as que vieram depois moram no
    # migracoes.sql. Rodar os dois deixa o banco novo igual ao banco de quem já
    # usa o sistema há meses.
    db.aplicar_migracoes()

    conexao = db.conectar()
    try:
        cursor = conexao.cursor()
        total_turmas = 0

        for ordem, m in enumerate(MODALIDADES, 1):
            cursor.execute(
                """
                INSERT INTO modalidade (slug, nome, genero, descricao, cor, icone,
                                        dias_aula, horario, tem_convocacao,
                                        termo_aluno, termo_aula, termo_aula_pl,
                                        artigo_aula, ordem)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (m["slug"], m["nome"], m["genero"], m["descricao"], m["cor"],
                 m["icone"], m["dias_aula"], m["horario"], m["tem_convocacao"],
                 m["termo_aluno"], m["termo_aula"], m["termo_aula_pl"],
                 m["artigo_aula"], ordem),
            )
            modalidade_id = cursor.lastrowid

            for ordem_turma, (turma_nome, _faixa) in enumerate(m["turmas"], 1):
                cursor.execute(
                    "INSERT INTO turma (modalidade_id, nome, ordem) VALUES (?,?,?)",
                    (modalidade_id, turma_nome, ordem_turma),
                )
                total_turmas += 1

            print(f"  {m['nome']} {m['genero']:<10} "
                  f"{len(m['turmas'])} turma(s) · {m['horario']}")

        conexao.commit()
        print(f"\n{len(MODALIDADES)} modalidades e {total_turmas} turmas gravadas.")
        print("Nenhuma pessoa cadastrada — o banco está pronto e vazio.")
    finally:
        conexao.close()


if __name__ == "__main__":
    configurar()
