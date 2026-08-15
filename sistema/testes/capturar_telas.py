"""
Gera as capturas de tela do sistema para o relatório e o vídeo pitch.

Salva em evidencias/telas/, na raiz do projeto.

Telas com barra fixa (a de salvar chamada) são capturadas só na viewport: numa
captura de página inteira a barra é pintada no meio do conteúdo e pareceria um
defeito no relatório.

São três passagens, porque o sistema mostra coisas diferentes pra cada um:
a coordenação logada, o participante logado, e quem ainda não entrou.

Uso:  python testes/capturar_telas.py   (com o app rodando)
"""

import secrets
from pathlib import Path

from playwright.sync_api import sync_playwright

import _acesso
import autenticacao
import db

BASE = "http://127.0.0.1:5000"

# O destino estava escrito à mão como C:\PROJETOS\..., a pasta do meu
# computador. Fora dela o script criava a árvore inteira com esse nome no
# diretório atual e salvava os prints lá dentro, sem reclamar de nada. Agora sai
# da posição deste arquivo: testes/ -> sistema/ -> raiz do projeto.
DESTINO = Path(__file__).resolve().parent.parent.parent / "evidencias" / "telas"
DESTINO.mkdir(parents=True, exist_ok=True)

LOGIN_JOGADOR = "teste-automatizado-jogador"

# (nome do arquivo, rota, captura a página inteira?)
DESKTOP = [
    ("desktop-01-centro", "/", True),
    ("desktop-02-painel", "/m/futebol-masculino", True),
    ("desktop-03-alunos", "/m/futebol-masculino/alunos", True),
    ("desktop-04-pessoa", "/pessoas/1", True),
    ("desktop-05-agenda", "/m/futebol-masculino/agenda", True),
    ("desktop-06-chamada", "/m/futebol-masculino/chamada", False),
    ("desktop-07-convocacao", "/convocacao/1", False),
    ("desktop-08-configuracoes", "/configuracoes", True),
    ("desktop-09-acessos", "/usuarios", True),
    ("desktop-10-planos", "/m/futebol-masculino/planos", True),
    ("desktop-11-plano-novo", "/m/futebol-masculino/planos/novo", True),
    ("desktop-12-horario", "/m/futebol-masculino/horario", True),
    ("desktop-13-matricula", "/matriculas/1/editar", True),
]

CELULAR = [
    ("celular-01-centro", "/", True),
    ("celular-02-painel", "/m/futebol-masculino", True),
    ("celular-03-pessoas", "/pessoas", True),
    ("celular-04-pessoa", "/pessoas/1", True),
    ("celular-05-chamada", "/m/futebol-masculino/chamada", False),
    ("celular-06-agenda", "/m/karate/agenda", True),
    ("celular-07-matricular", "/m/futebol-masculino/matricular", True),
    ("celular-08-planos", "/m/futebol-masculino/planos", True),
]

# A área do participante. Precisa de outra conta: como admin ela abre dizendo
# "sua conta não está ligada a um cadastro", que é o contrário do que o print
# tem que mostrar. É aqui que o plano de treino aparece pra quem treina, então
# pro pitch esta é a imagem que importa.
DO_JOGADOR = [
    ("desktop-14-minha-area", "/minha-area", True),
]

DO_JOGADOR_CELULAR = [
    ("celular-09-minha-area", "/minha-area", True),
]

# A tela de entrar só existe pra quem NÃO entrou. Na lista de cima ela sairia
# como um redirecionamento pro Centro, e o print seria de outra tela.
SEM_LOGIN = [
    ("desktop-00-entrar", "/entrar", True),
]

SEM_LOGIN_CELULAR = [
    ("celular-00-entrar", "/entrar", True),
]


def preparar_jogador():
    """
    Acesso de participante, ligado a alguém que de fato treina.

    Mesmo tratamento da conta de admin do _acesso: senha aleatória, criada
    agora e apagada no fim. Escolho alguém do futebol masculino porque é a
    modalidade que tem plano de treino publicado na base de demonstração. Sem
    isso o print sairia com a seção de treinos vazia.

    Devolve (login, senha), ou (None, None) se não houver ninguém matriculado.
    """
    conexao = db.conectar()
    try:
        pessoa = conexao.execute(
            """
            SELECT p.id FROM pessoa p
            JOIN matricula ma ON ma.pessoa_id = p.id
            JOIN turma t      ON t.id = ma.turma_id
            JOIN modalidade m ON m.id = t.modalidade_id
            WHERE m.slug = 'futebol-masculino' AND ma.status = 'ativa'
            LIMIT 1
            """
        ).fetchone()
        if pessoa is None:
            return None, None

        senha = secrets.token_urlsafe(18)
        conexao.execute("DELETE FROM usuario WHERE login = ?", (LOGIN_JOGADOR,))
        conexao.execute(
            "INSERT INTO usuario (login, senha_hash, papel, pessoa_id) "
            "VALUES (?,?,'jogador',?)",
            (LOGIN_JOGADOR, autenticacao.hash_da_senha(senha), pessoa["id"]),
        )
        conexao.commit()
        return LOGIN_JOGADOR, senha
    finally:
        conexao.close()


def remover_jogador():
    conexao = db.conectar()
    try:
        conexao.execute("DELETE FROM usuario WHERE login = ?", (LOGIN_JOGADOR,))
        conexao.commit()
    finally:
        conexao.close()


def entrar_como(pagina, login, senha):
    """Login pelo formulário. Estoura se não entrar, pra não capturar às cegas."""
    pagina.goto(f"{BASE}/entrar", wait_until="networkidle")
    pagina.fill("#login", login)
    pagina.fill("#senha", senha)
    pagina.click("button[type=submit]")
    pagina.wait_for_load_state("networkidle")
    if "/entrar" in pagina.url:
        raise RuntimeError(f"não entrei como {login!r}. Os prints sairiam da "
                           f"tela de login e eu não perceberia.")


def capturar(contexto, telas, login=None, senha=None):
    pagina = contexto.new_page()
    # Cada contexto é um navegador limpo, sem cookie: precisa entrar de novo,
    # senão os prints saem todos da tela de login. Sem login nenhum é o caso da
    # própria tela de entrar.
    if login:
        entrar_como(pagina, login, senha)
    for nome, rota, inteira in telas:
        resposta = pagina.goto(BASE + rota, wait_until="networkidle")
        if resposta.status != 200:
            print(f"  PULOU {nome}: HTTP {resposta.status} em {rota}")
            continue
        # O limite padrão do Playwright é 30s e a lista de pessoas estoura ele:
        # no celular, a página inteira das 62 pessoas a 390px com escala 3 vira
        # uma imagem de milhares de pixels de altura. Em máquina lenta o print
        # falhava no meio da rodada e derrubava a captura inteira, depois de já
        # ter gerado metade dos arquivos.
        pagina.screenshot(path=DESTINO / f"{nome}.png", full_page=inteira,
                          timeout=180_000)
        print(f"  {nome}.png")
    pagina.close()


senha_teste = _acesso.preparar_admin()
login_jogador, senha_jogador = preparar_jogador()
if login_jogador is None:
    print("AVISO: ninguém matriculado no futebol masculino. A área do "
          "participante não vai ser capturada.")

TELA_DESKTOP = {"viewport": {"width": 1440, "height": 900},
                "device_scale_factor": 2}
TELA_CELULAR = {"viewport": {"width": 390, "height": 844},
                "device_scale_factor": 3, "is_mobile": True, "has_touch": True}

with sync_playwright() as p:
    navegador = p.chromium.launch(channel="chrome")

    for descricao, tela, sem_login, admin, jogador in [
        ("Computador", TELA_DESKTOP, SEM_LOGIN, DESKTOP, DO_JOGADOR),
        # Celular do técnico à beira do campo.
        ("Celular", TELA_CELULAR, SEM_LOGIN_CELULAR, CELULAR, DO_JOGADOR_CELULAR),
    ]:
        print(f"\n{descricao}")

        ctx = navegador.new_context(**tela)
        capturar(ctx, sem_login)
        ctx.close()

        ctx = navegador.new_context(**tela)
        capturar(ctx, admin, _acesso.LOGIN_TESTE, senha_teste)
        ctx.close()

        if login_jogador:
            ctx = navegador.new_context(**tela)
            capturar(ctx, jogador, login_jogador, senha_jogador)
            ctx.close()

    navegador.close()

_acesso.remover_admin()
remover_jogador()

print(f"\nCapturas salvas em {DESTINO}")
