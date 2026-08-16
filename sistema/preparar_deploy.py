"""
Prepara o banco na hospedagem, sem terminal e sem ninguém digitando nada.

Por que isto existe: no plano gratuito do Render não há disco persistente. O
sistema de arquivos volta ao estado do deploy a cada reinício, e o banco é um
arquivo — some junto. Então em vez de tentar preservar, eu reconstruo: cada
início devolve uma base de demonstração conhecida e completa, em vez de um banco
pela metade ou inexistente.

Isso é aceitável porque a instância hospedada é uma DEMONSTRAÇÃO. Os 62 nomes
são fictícios. O que for digitado nela se perde no próximo reinício, e está
documentado assim.

    A instância hospedada nunca recebe o caderno real do Centro. Dado real de
    criança fica na rede local, onde a seção 4 do DECISOES.md pode sustentar as
    escolhas de segurança. Isto aqui é vitrine.

Uso:
    python preparar_deploy.py

Variáveis de ambiente:
    ADMIN_LOGIN   login do administrador (padrão: coordenacao)
    ADMIN_SENHA   senha dele — OBRIGATÓRIA, sem padrão de propósito
    DEMO_LOGIN    login da conta de demonstração (padrão: demo)
    DEMO_SENHA    senha dela (padrão: demo2026)
    DEMO_ATIVA    0 desliga a conta de demonstração
"""

import os
import sys
from datetime import date, timedelta
from pathlib import Path

import autenticacao
import configurar
import db
import escalacao
import importar

PASTA_DADOS = Path(__file__).resolve().parent / "dados"

PLANILHAS = [
    PASTA_DADOS / "demonstracao-matriculas.csv",
    PASTA_DADOS / "demonstracao-presencas.csv",
]


def criar_eventos(conexao) -> int:
    """
    Jogos de exemplo, com convocação. Datas relativas a hoje: jogo de data
    passada mostra "nenhum jogo próximo" e parece defeito.
    """
    hoje = date.today()

    # A TURMA de cada jogo tem que ser uma que TENHA GENTE. Eu tinha posto o
    # amistoso feminino no Sub-15, que na base ficou vazio: o evento existia, a
    # tela abria, e a escalação mostrava 11 posições sem ninguém pra escolher —
    # parecia defeito do sistema. Depois de conferir a base, os dois jogos de
    # futebol vão pro Sub-13, que é onde os times fecham.
    jogos = [
        ("futsal-masculino", "Sub-13", "Copa Regional de Base — 1ª rodada",
         "Grêmio do Jardim Maria Rosa", hoje + timedelta(days=9),
         "Campo do Centro de Cultura e Esportes",
         "Chegar 40 minutos antes, uniforme completo."),
        ("futsal-feminino", "Sub-13", "Amistoso de preparação",
         "Meninas do Parque Pinheiros", hoje + timedelta(days=16),
         "Quadra da Escola Estadual Jardim Record", None),
        # Sub-13 e não Sub-15: só o Sub-13 tem 11 pessoas pra fechar o time. Com
        # o Sub-15 o próprio preparar_deploy avisava "9 elegíveis para 11
        # posições" e a tela de escalação subia com buraco no campo.
        ("futsal-masculino", "Sub-13", "Torneio interbairros",
         "União Taboão", hoje - timedelta(days=5),
         "Campo do Centro de Cultura e Esportes",
         "Levar documento com foto."),
    ]

    criados = 0
    for slug, turma_nome, nome, adversario, dia, local, observacoes in jogos:
        modalidade = conexao.execute(
            "SELECT id FROM modalidade WHERE slug = ?", (slug,)
        ).fetchone()
        if modalidade is None:
            continue

        turma_id = None
        if turma_nome:
            turma = conexao.execute(
                "SELECT id FROM turma WHERE modalidade_id = ? AND nome = ?",
                (modalidade["id"], turma_nome),
            ).fetchone()
            turma_id = turma["id"] if turma else None

        cursor = conexao.execute(
            """
            INSERT INTO evento (modalidade_id, turma_id, nome, adversario,
                                data, local, observacoes)
            VALUES (?,?,?,?,?,?,?)
            """,
            (modalidade["id"], turma_id, nome, adversario, dia, local, observacoes),
        )
        criados += 1

        # Convoco quem está nessa turma (ou na modalidade, se o jogo for dela
        # inteira), pra tela de convocação ter conteúdo e a mensagem de WhatsApp
        # sair preenchida.
        if turma_id:
            elegiveis = conexao.execute(
                "SELECT id FROM matricula WHERE turma_id = ? AND status = 'ativa' "
                "LIMIT 14", (turma_id,)
            ).fetchall()
        else:
            elegiveis = conexao.execute(
                """SELECT ma.id FROM matricula ma JOIN turma t ON t.id = ma.turma_id
                   WHERE t.modalidade_id = ? AND ma.status = 'ativa' LIMIT 14""",
                (modalidade["id"],),
            ).fetchall()

        conexao.executemany(
            "INSERT INTO convocacao (evento_id, matricula_id) VALUES (?,?)",
            [(cursor.lastrowid, e["id"]) for e in elegiveis],
        )

        # Confere se dá pra montar o time. Se não der, avisa em vez de deixar a
        # tela de escalação com posições vazias parecendo defeito. Foi exatamente
        # isso que aconteceu quando um jogo apontou pra turma sem gente.
        _quadra, posicoes = escalacao.para_modalidade(slug)
        if posicoes and len(elegiveis) < len(posicoes):
            print(f"  AVISO: {nome} tem {len(elegiveis)} elegíveis para "
                  f"{len(posicoes)} posições — o time não fecha.")

        # O PRIMEIRO jogo já sobe escalado, pra vitrine mostrar o campo montado.
        # Os outros ficam com todo mundo no banco, que é como o técnico encontra
        # um jogo novo antes de escalar.
        if criados == 1 and posicoes:
            for (codigo, _c, _n, _x, _y), pessoa in zip(posicoes, elegiveis):
                conexao.execute(
                    "UPDATE convocacao SET posicao = ? "
                    "WHERE evento_id = ? AND matricula_id = ?",
                    (codigo, cursor.lastrowid, pessoa["id"]),
                )

    conexao.commit()
    print(f"  {criados} evento(s) de exemplo, com convocação")
    return 0


def criar_planos(conexao) -> int:
    """Planos de exemplo, senão a tela da vitrine sobe vazia."""
    hoje = date.today()

    planos = [
        ("futsal-masculino", "Sub-13", hoje + timedelta(days=1),
         "Finalização e jogo coletivo",
         "Aquecimento e corrida leve — 15min\n"
         "Passe em duplas, dois toques\n"
         "Finalização de fora da área\n"
         "Coletivo 20min",
         "Caneleira e garrafa de água"),
        ("futsal-masculino", None, hoje + timedelta(days=3),
         "Treino físico",
         "Circuito de resistência\nTiros de 30m\nAlongamento",
         None),
        ("jiu-jitsu", None, hoje,
         "Barra e alongamento",
         "Aquecimento no chão\nExercícios de barra\n"
         "Posições de pés\nAlongamento",
         "Sapatilha e meia-calça"),
        ("jiu-jitsu", "Faixa branca", hoje + timedelta(days=2),
         "Kihon — base e postura",
         "Aquecimento\nZenkutsu-dachi, repetição\n"
         "Oi-zuki descendo o dojo\nAlongamento e meditação",
         "Kimono lavado"),
    ]

    criados = 0
    for slug, turma_nome, dia, titulo, conteudo, material in planos:
        modalidade = conexao.execute(
            "SELECT id FROM modalidade WHERE slug = ?", (slug,)
        ).fetchone()
        if modalidade is None:
            continue

        turma_id = None
        if turma_nome:
            turma = conexao.execute(
                "SELECT id FROM turma WHERE modalidade_id = ? AND nome = ?",
                (modalidade["id"], turma_nome),
            ).fetchone()
            turma_id = turma["id"] if turma else None

        conexao.execute(
            """
            INSERT INTO plano_treino (modalidade_id, turma_id, data, titulo,
                                      conteudo, material)
            VALUES (?,?,?,?,?,?)
            """,
            (modalidade["id"], turma_id, dia, titulo, conteudo, material),
        )
        criados += 1

    conexao.commit()
    print(f"  {criados} plano(s) de treino de exemplo")
    return 0


def criar_admin(conexao) -> int:
    """
    Garante um administrador. Sem senha no ambiente, aborta.

    Não invento senha padrão: um sistema hospedado com admin de senha conhecida
    é pior que um sistema sem login, porque dá a impressão de estar protegido.
    """
    login = os.environ.get("ADMIN_LOGIN", "coordenacao").strip()
    senha = os.environ.get("ADMIN_SENHA", "")

    if not senha:
        print("ERRO: defina ADMIN_SENHA no ambiente antes de subir.")
        print("      Sem ela eu não crio administrador, e sem administrador")
        print("      ninguém entra no sistema.")
        return 1

    if len(senha) < autenticacao.MINIMO_SENHA:
        print(f"ERRO: ADMIN_SENHA precisa de pelo menos "
              f"{autenticacao.MINIMO_SENHA} caracteres.")
        return 1

    erro = autenticacao.criar_usuario(conexao, login, senha, "admin", None)
    if erro:
        print(f"ERRO ao criar o administrador: {erro}")
        return 1

    print(f"  administrador {login!r} criado")
    return 0


def criar_demo(conexao) -> int:
    """
    Conta de demonstração da vitrine, com senha conhecida. Só existe porque este
    arquivo roda apenas na hospedagem, sobre base inventada que some a cada
    reinício — no computador do Centro ele nunca executa. DEMO_ATIVA=0 desliga.
    """
    if os.environ.get("DEMO_ATIVA", "1") == "0":
        print("  conta de demonstração desligada (DEMO_ATIVA=0)")
        return 0

    login = os.environ.get("DEMO_LOGIN", "demo").strip()
    senha = os.environ.get("DEMO_SENHA", "demo2026")

    erro = autenticacao.criar_usuario(conexao, login, senha, "admin", None)
    if erro:
        # Não derruba o deploy por causa da conta de demonstração: o sistema
        # ainda sobe e o admin de verdade continua entrando. Só avisa.
        print(f"  AVISO: conta de demonstração não criada: {erro}")
        return 0

    print(f"  conta de demonstração {login!r} criada (base fictícia)")
    return 0


def main() -> int:
    print("Preparando a base de demonstração...")

    faltando = [p for p in PLANILHAS if not p.exists()]
    if faltando:
        print("ERRO: não achei as planilhas de demonstração:")
        for p in faltando:
            print(f"      {p}")
        return 1

    # Recriar sempre, e não só quando falta: assim o estado é o mesmo em todo
    # início, sem depender de o que sobrou do reinício anterior.
    configurar.configurar()

    conexao = db.conectar()
    try:
        resultado = importar.Resultado()
        for planilha in PLANILHAS:
            importar.importar_arquivo(conexao, planilha, resultado)

        for linha in resultado.resumo:
            print(f"  {linha.strip()}")

        if resultado.erros:
            print(f"\nERRO: {len(resultado.erros)} linha(s) não entraram:")
            for e in resultado.erros[:10]:
                print(f"      {e}")
            return 1

        codigo = criar_eventos(conexao)
        if codigo:
            return codigo

        codigo = criar_planos(conexao)
        if codigo:
            return codigo

        codigo = criar_admin(conexao)
        if codigo:
            return codigo

        codigo = criar_demo(conexao)
        if codigo:
            return codigo

        estado = importar.estado_do_banco(conexao)
    finally:
        conexao.close()

    print(f"\nPronto: {estado['pessoas']} pessoas, {estado['matriculas']} "
          f"matrículas, {estado['presencas']} presenças, "
          f"{estado['eventos']} evento(s).")
    print("Lembrete: esta base é FICTÍCIA e some no próximo reinício.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
